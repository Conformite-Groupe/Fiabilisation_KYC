# -*- coding: utf-8 -*-
"""Crée les lignes SidebarAccess manquantes, une par organe.

Tant qu'un organe n'a pas sa ligne, `SidebarAccess.perms_for()` retombe sur
`legacy_perms_for_organe()` — la règle historique codée en dur — et l'admin
n'a donc aucune prise sur la sidebar de cet organe.

Les lignes créées reprennent exactement la règle historique : le comportement
de la plateforme est inchangé juste après l'exécution, mais tout devient
modifiable depuis /admin/kyc/sidebaraccess/.

    python manage.py seed_sidebar_access --dry-run
    python manage.py seed_sidebar_access
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organe
from kyc.models import SidebarAccess


class Command(BaseCommand):
    help = ("Crée les lignes SidebarAccess manquantes à partir de la règle historique, "
            "pour rendre chaque organe modifiable dans l'admin.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Affiche les créations sans rien écrire.")
        parser.add_argument("--reset", action="store_true",
                            help="Réécrit AUSSI les lignes existantes avec la règle "
                                 "historique. Écrase les réglages faits dans l'admin.")

    @transaction.atomic
    def handle(self, *args, **options):
        dry = options["dry_run"]
        reset = options["reset"]
        crees = reinitialises = 0

        for valeur, _ in Organe:
            defauts = SidebarAccess.legacy_perms_for_organe(valeur)
            ligne = SidebarAccess.objects.filter(organe=valeur).first()

            if ligne is None:
                actives = sorted(p for p, v in defauts.items() if v)
                self.stdout.write(f"[CREE]  {valeur:30s} {', '.join(actives) or 'aucune permission'}")
                crees += 1
                if not dry:
                    SidebarAccess.objects.create(organe=valeur, **defauts)
            elif reset:
                ecarts = [p for p in SidebarAccess.ALL_PERMS
                          if getattr(ligne, p) != defauts[p]]
                if ecarts:
                    self.stdout.write(self.style.WARNING(
                        f"[RESET] {valeur:30s} {len(ecarts)} case(s) écrasée(s) : "
                        f"{', '.join(ecarts)}"))
                    reinitialises += 1
                    if not dry:
                        for champ in ecarts:
                            setattr(ligne, champ, defauts[champ])
                        ligne.save(update_fields=ecarts)
            else:
                self.stdout.write(f"[OK]    {valeur:30s} pk={ligne.pk} (inchangée)")

        total = SidebarAccess.objects.count()
        resume = (f"{crees} créée(s), {reinitialises} réinitialisée(s) — "
                  f"{total} ligne(s) au total.")
        if dry:
            self.stdout.write(self.style.WARNING(f"[DRY-RUN] Aucune écriture. {resume}"))
            transaction.set_rollback(True)
        else:
            self.stdout.write(self.style.SUCCESS(resume))
