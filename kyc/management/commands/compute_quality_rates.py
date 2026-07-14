"""Précalcule le taux de qualité PP/PM par scope et le stocke dans TauxQualite.

A lancer chaque matin APRES les imports (import_premier.py, import_taux_agent.py).
Le dashboard (vue `statistiques`) lit ensuite cette table au lieu de rescanner
Kyc_pp (1,1 M de lignes) à chaque affichage.

Le taux est calculé à l'identique de `compute_quality_rate_by_typology` dans
kyc/views.py : pour un scope donné, somme(ok_count)/somme(total) sur toutes les
règles actives de la typologie, arrondi à 1 décimale.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from kyc.models import DataQualityRule, TauxQualite
from kyc.views import evaluate_data_quality_rule, evaluate_data_quality_scope


class Command(BaseCommand):
    help = "Précalcule le taux de qualité PP/PM par scope dans la table TauxQualite."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", type=str, default=None,
            help="Date de calcul au format YYYY-MM-DD (défaut : aujourd'hui).",
        )
        parser.add_argument(
            "--prune-days", type=int, default=30,
            help="Supprime les enregistrements plus vieux que N jours (0 = ne rien purger).",
        )

    def handle(self, *args, **options):
        if options["date"]:
            from datetime import datetime
            target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
        else:
            target_date = timezone.localdate()

        scopes = self._distinct_scopes()
        self.stdout.write(f"{len(scopes)} scope(s) distinct(s) à calculer pour le {target_date}.")

        written = 0
        for filiale, agence, expl in scopes:
            for applicability in ("PP", "PM"):
                ok_count, total = self._compute_scope(applicability, filiale, agence, expl)
                rate = round(ok_count / total * 100, 1) if total else 0
                TauxQualite.objects.update_or_create(
                    filiale=filiale, agence=agence, expl=expl,
                    applicability=applicability, date=target_date,
                    defaults={"rate": rate, "ok_count": ok_count, "total": total},
                )
                written += 1

        pruned = 0
        prune_days = options["prune_days"]
        if prune_days > 0:
            from datetime import timedelta
            cutoff = target_date - timedelta(days=prune_days)
            pruned = TauxQualite.objects.filter(date__lt=cutoff).delete()[0]

        self.stdout.write(self.style.SUCCESS(
            f"TauxQualite : {written} lignes écrites, {pruned} anciennes lignes purgées."
        ))

    def _distinct_scopes(self):
        """Scopes réellement affichés = scope de chaque utilisateur actif.

        On dérive le scope via la MÊME fonction que le dashboard
        (evaluate_data_quality_scope) pour garantir une correspondance exacte
        lors de la lecture, puis on déduplique.
        """
        User = get_user_model()
        seen = set()
        scopes = []
        for user in User.objects.filter(is_active=True):
            s = evaluate_data_quality_scope(user)
            key = (s.get("filiale"), s.get("agence"), s.get("expl"))
            if key in seen:
                continue
            seen.add(key)
            scopes.append(key)
        return scopes

    def _compute_scope(self, applicability, filiale, agence, expl):
        rules = list(DataQualityRule.objects.filter(active=True, applicability=applicability))
        total_ok = 0
        total_evaluated = 0
        for rule in rules:
            stat = evaluate_data_quality_rule(rule, filiale=filiale, agence=agence, expl=expl)
            total_ok += stat.get("ok_count", 0)
            total_evaluated += stat.get("total", 0)
        return total_ok, total_evaluated
