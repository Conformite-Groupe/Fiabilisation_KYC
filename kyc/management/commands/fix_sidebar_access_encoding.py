# -*- coding: utf-8 -*-
"""Nettoie les lignes SidebarAccess dont l'organe est en mojibake.

Symptôme corrigé : la table contient des doublons (« Conformité » ET
« ConformitÃ© »). Comme `SidebarAccess.perms_for()` cherche d'abord une
correspondance exacte avec l'organe de l'utilisateur — toujours stocké dans sa
forme correcte —, seule la ligne propre est appliquée. Modifier la ligne
mojibake dans l'admin n'a alors aucun effet sur la sidebar.

Deux cas traités :
  - un jumeau propre existe  -> la ligne mojibake est supprimée
    (si elle diffère du jumeau, ses valeurs sont ignorées sauf --prefer-mojibake) ;
  - aucun jumeau propre      -> la ligne est renommée dans sa forme correcte.

    python manage.py fix_sidebar_access_encoding --dry-run
    python manage.py fix_sidebar_access_encoding
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from kyc.models import SidebarAccess


def demojibake(valeur):
    """« ConformitÃ© » -> « Conformité ». None si la chaîne n'est pas du mojibake."""
    try:
        corrige = valeur.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return corrige if corrige != valeur else None


class Command(BaseCommand):
    help = ("Fusionne / renomme les lignes SidebarAccess dont l'organe est encodé "
            "en mojibake (Ã© au lieu de é).")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Affiche les actions sans rien modifier.")
        parser.add_argument("--prefer-mojibake", action="store_true",
                            help="En cas de valeurs divergentes, recopie les cases de la "
                                 "ligne mojibake sur la ligne propre avant suppression. "
                                 "Par défaut la ligne propre fait foi.")

    @transaction.atomic
    def handle(self, *args, **options):
        dry = options["dry_run"]
        prefer_mojibake = options["prefer_mojibake"]
        perms = SidebarAccess.ALL_PERMS
        renommes = supprimes = fusionnes = 0

        for ligne in SidebarAccess.objects.order_by("pk"):
            propre = demojibake(ligne.organe)
            if not propre:
                continue

            jumeau = SidebarAccess.objects.filter(organe=propre).exclude(pk=ligne.pk).first()

            if jumeau is None:
                self.stdout.write(f"[RENOMME] pk={ligne.pk} « {ligne.organe} » -> « {propre} »")
                renommes += 1
                if not dry:
                    ligne.organe = propre
                    ligne.save(update_fields=["organe"])
                continue

            divergences = {p: (getattr(ligne, p), getattr(jumeau, p))
                           for p in perms if getattr(ligne, p) != getattr(jumeau, p)}
            if divergences and prefer_mojibake:
                self.stdout.write(
                    f"[FUSION]   pk={ligne.pk} « {ligne.organe} » -> pk={jumeau.pk} "
                    f"« {propre} » : {len(divergences)} case(s) recopiée(s) "
                    f"({', '.join(sorted(divergences))})")
                fusionnes += 1
                if not dry:
                    for champ in divergences:
                        setattr(jumeau, champ, getattr(ligne, champ))
                    jumeau.save(update_fields=list(divergences))
            elif divergences:
                self.stdout.write(self.style.WARNING(
                    f"[ECART]    pk={ligne.pk} « {ligne.organe} » diverge de pk={jumeau.pk} "
                    f"sur : {', '.join(sorted(divergences))} — la ligne propre est conservée "
                    f"(utiliser --prefer-mojibake pour l'inverse)."))

            self.stdout.write(f"[SUPPRIME] pk={ligne.pk} « {ligne.organe} » "
                              f"(doublon de pk={jumeau.pk})")
            supprimes += 1
            if not dry:
                ligne.delete()

        total = SidebarAccess.objects.count()
        resume = (f"{renommes} renommée(s), {fusionnes} fusionnée(s), "
                  f"{supprimes} supprimée(s) — {total} ligne(s) restantes.")
        if dry:
            self.stdout.write(self.style.WARNING(f"[DRY-RUN] Aucune écriture. {resume}"))
            transaction.set_rollback(True)
        else:
            self.stdout.write(self.style.SUCCESS(resume))
