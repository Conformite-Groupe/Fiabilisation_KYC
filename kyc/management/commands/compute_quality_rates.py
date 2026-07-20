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
from kyc.views import evaluate_data_quality_rule, evaluate_data_quality_scope, flux_datouv_window


class Command(BaseCommand):
    help = "Précalcule le taux de qualité PP/PM par scope dans la table TauxQualite."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", type=str, default=None,
            help="Date de calcul au format YYYY-MM-DD (défaut : aujourd'hui).",
        )
        parser.add_argument(
            "--prune-days", type=int, default=400,
            help="Supprime les enregistrements plus vieux que N jours (0 = ne rien purger). "
                 "Défaut 400 : l'historique sert à étudier l'évolution des taux stock/flux.",
        )
        parser.add_argument(
            "--skip-flux", action="store_true",
            help="Ne calcule pas le taux flux (fenêtre DATOUV), seulement le stock.",
        )
        parser.add_argument(
            "--flux-only", action="store_true",
            help="Ne calcule que le taux flux (rapide : la fenêtre DATOUV réduit fortement le volume).",
        )
        parser.add_argument(
            "--slice", type=str, default="1/1",
            help="Découpage parallèle des scopes, format i/N (ex. 2/6 = worker 2 sur 6). "
                 "Chaque worker traite un sous-ensemble disjoint ; seul le worker 1 purge.",
        )

    def handle(self, *args, **options):
        if options["date"]:
            from datetime import datetime
            target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
        else:
            target_date = timezone.localdate()

        # --slice i/N : répartit les scopes (triés) en N sous-ensembles disjoints
        # via un pas (stride), comme warm_ui_caches. Permet N workers parallèles.
        try:
            slice_idx, slice_total = (int(x) for x in options["slice"].split("/"))
        except (ValueError, AttributeError):
            slice_idx, slice_total = 1, 1
        if slice_total < 1 or not (1 <= slice_idx <= slice_total):
            slice_idx, slice_total = 1, 1

        scopes = self._distinct_scopes()
        scopes = sorted(scopes, key=lambda s: tuple(x or "" for x in s))
        if slice_total > 1:
            scopes = scopes[slice_idx - 1::slice_total]
        self.stdout.write(f"{len(scopes)} scope(s) distinct(s) à calculer pour le {target_date} "
                          f"(slice {slice_idx}/{slice_total}).")

        # Calcul d'abord (lectures seules, la partie longue), écritures groupées
        # à la fin : sur SQLite un seul écrivain à la fois, on garde la fenêtre
        # d'écriture minimale pour ne pas bloquer les autres workers.
        # Modes calculés : stock (toute la base, comportement historique) et
        # flux (clients dont DATOUV tombe dans la fenêtre configurée dans
        # l'admin : veille ou mois précédent).
        modes = [] if options["flux_only"] else [("stock", None, None)]
        if not options["skip_flux"]:
            flux_start, flux_end = flux_datouv_window(target_date)
            modes.append(("flux", flux_start, flux_end))
            self.stdout.write(f"Fenêtre flux (DATOUV) : {flux_start} -> {flux_end}.")

        rows = []
        for filiale, agence, expl in scopes:
            for applicability in ("PP", "PM"):
                for flux_stock, d_start, d_end in modes:
                    ok_count, total = self._compute_scope(
                        applicability, filiale, agence, expl,
                        datouv_start=d_start, datouv_end=d_end,
                    )
                    rate = round(ok_count / total * 100, 1) if total else 0
                    rows.append((filiale, agence, expl, applicability, flux_stock,
                                 {"rate": rate, "ok_count": ok_count, "total": total}))

        written = self._write_rows(rows, target_date)

        pruned = 0
        prune_days = options["prune_days"]
        # Un seul worker purge (le 1er) pour éviter les suppressions concurrentes.
        if prune_days > 0 and slice_idx == 1:
            from datetime import timedelta
            cutoff = target_date - timedelta(days=prune_days)
            pruned = TauxQualite.objects.filter(date__lt=cutoff).delete()[0]

        self.stdout.write(self.style.SUCCESS(
            f"TauxQualite : {written} lignes écrites, {pruned} anciennes lignes purgées."
        ))

    def _write_rows(self, rows, target_date):
        """Écrit toutes les lignes en une transaction courte, avec reprise si la
        base SQLite est verrouillée par un autre worker."""
        import time
        from django.db import transaction
        from django.db.utils import OperationalError

        written = 0
        for attempt in range(5):
            try:
                with transaction.atomic():
                    written = 0
                    for filiale, agence, expl, applicability, flux_stock, defaults in rows:
                        TauxQualite.objects.update_or_create(
                            filiale=filiale, agence=agence, expl=expl,
                            applicability=applicability, flux_stock=flux_stock,
                            date=target_date,
                            defaults=defaults,
                        )
                        written += 1
                return written
            except OperationalError as e:
                if "locked" not in str(e).lower() or attempt == 4:
                    raise
                wait = 5 * (attempt + 1)
                self.stdout.write(f"Base verrouillée, nouvel essai dans {wait}s "
                                  f"(tentative {attempt + 2}/5)...")
                time.sleep(wait)
        return written

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

    def _compute_scope(self, applicability, filiale, agence, expl,
                       datouv_start=None, datouv_end=None):
        rules = list(DataQualityRule.objects.filter(active=True, applicability=applicability))
        total_ok = 0
        total_evaluated = 0
        for rule in rules:
            stat = evaluate_data_quality_rule(
                rule, filiale=filiale, agence=agence, expl=expl,
                datouv_start=datouv_start, datouv_end=datouv_end,
            )
            total_ok += stat.get("ok_count", 0)
            total_evaluated += stat.get("total", 0)
        return total_ok, total_evaluated
