# -*- coding: utf-8 -*-
"""Diagnostic des habilitations de la sidebar.

Explique, pour un utilisateur ou pour tous les organes, POURQUOI une entrée de
menu apparaît ou non :
  - la ligne SidebarAccess existe-t-elle pour cet organe (sinon : règle
    historique `legacy_perms_for_organe`, non modifiable dans l'admin) ;
  - le compte est-il superuser (toutes les permissions forcées à True) ;
  - l'entrée « Screening KYC ID » exige EN PLUS
    FilialeModuleConfig.screening_kyc_paye_active pour la filiale du compte.

    python manage.py diag_sidebar_access
    python manage.py diag_sidebar_access --user cf@boasenegal.com
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Organe
from kyc.models import FilialeModuleConfig, SidebarAccess


class Command(BaseCommand):
    help = "Diagnostique les habilitations de la sidebar (SidebarAccess + modules filiale)."

    def add_arguments(self, parser):
        parser.add_argument("--user", default="",
                            help="Nom d'utilisateur à diagnostiquer. Vide = tous les organes.")
        parser.add_argument("--perm", default="",
                            help="N'afficher qu'une permission (ex. screening_kyc).")

    def handle(self, *args, **options):
        username = (options["user"] or "").strip()
        perm_filtre = (options["perm"] or "").strip()

        self.stdout.write(self.style.MIGRATE_HEADING("\n1. Lignes SidebarAccess par organe"))
        manquants = []
        for valeur, _ in Organe:
            ligne = SidebarAccess.objects.filter(organe=valeur).first()
            if ligne:
                self.stdout.write(f"   [ADMIN ] {valeur:30s} pk={ligne.pk}")
            else:
                manquants.append(valeur)
                self.stdout.write(self.style.WARNING(
                    f"   [LEGACY] {valeur:30s} aucune ligne -> règle historique, "
                    f"l'admin n'a aucun effet"))
        if manquants:
            self.stdout.write(self.style.WARNING(
                f"\n   {len(manquants)} organe(s) sans ligne : "
                f"python manage.py seed_sidebar_access"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n2. Module Screening KYC par filiale"))
        configs = {c.filiale: c for c in FilialeModuleConfig.objects.all()}
        if not configs:
            self.stdout.write(self.style.WARNING(
                "   Aucune FilialeModuleConfig : « Screening KYC ID » est masqué pour TOUT LE MONDE.\n"
                "   -> /admin/kyc/filialemoduleconfig/add/ , cocher « Module Screening KYC PAYE actif »."))
        for filiale, config in sorted(configs.items()):
            etat = "ACTIF" if config.screening_kyc_paye_active else "INACTIF"
            style = self.style.SUCCESS if config.screening_kyc_paye_active else self.style.WARNING
            self.stdout.write(style(f"   [{etat:7s}] {filiale}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n3. Utilisateurs"))
        User = get_user_model()
        qs = User.objects.filter(username=username) if username else User.objects.all()
        if username and not qs.exists():
            self.stdout.write(self.style.ERROR(f"   Utilisateur introuvable : {username}"))
            return

        for user in qs.order_by("username"):
            perms = SidebarAccess.perms_for(user)
            ligne = SidebarAccess.objects.filter(organe=user.organe).first()
            if user.is_superuser:
                source = "SUPERUSER (toutes permissions forcées à True)"
            elif ligne:
                source = f"ligne admin pk={ligne.pk}"
            else:
                source = "règle historique (aucune ligne pour cet organe)"

            self.stdout.write(f"\n   {user.username}")
            self.stdout.write(f"     organe   : {user.organe}")
            self.stdout.write(f"     filiale  : {user.filiale}")
            self.stdout.write(f"     source   : {source}")

            if perm_filtre:
                self.stdout.write(f"     {perm_filtre} = {perms.get(perm_filtre)}")
            else:
                actives = sorted(p for p, v in perms.items() if v)
                self.stdout.write(f"     accordées: {', '.join(actives) or 'aucune'}")

            config = configs.get(user.filiale)
            module_ok = bool(config and config.screening_kyc_paye_active)
            visible = perms.get("screening_kyc") and module_ok
            detail = []
            if not perms.get("screening_kyc"):
                detail.append("SidebarAccess.screening_kyc décoché")
            if config is None:
                detail.append(f"aucune FilialeModuleConfig pour « {user.filiale} »")
            elif not config.screening_kyc_paye_active:
                detail.append(f"screening_kyc_paye_active décoché pour « {user.filiale} »")
            style = self.style.SUCCESS if visible else self.style.ERROR
            self.stdout.write(style(
                f"     Screening KYC ID : {'VISIBLE' if visible else 'MASQUÉ'}"
                + (f" — {' + '.join(detail)}" if detail else "")))
