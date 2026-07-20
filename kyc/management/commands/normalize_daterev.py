"""Normalise les champs date texte de Kyc_pp / Kyc_pm au format ISO 'YYYY-MM-DD'.

Les filtres d'échéance de /clients_scorer (DATEREV) et la fenêtre « flux » du
taux qualité (DATOUV) comparent ces champs lexicalement et supposent le format
ISO : des valeurs 'dd/mm/yyyy' ou 'dd/mm/yy' rendent les filtres faux. À lancer
une fois sur chaque base concernée :

    python manage.py normalize_daterev                    # DATEREV + DATOUV
    python manage.py normalize_daterev --fields DATEREV   # un seul champ
    python manage.py normalize_daterev --dry-run          # bilan sans écrire
"""
import re
from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from kyc.models import Kyc_pm, Kyc_pp

_DATE_RE_ISO = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_DATE_RE_FR = re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})")
_DATE_RE_FR_YY = re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2})$")


def normalize_date_text(value):
    """Année à 2 chiffres : pivot 50 (29 -> 2029, 87 -> 1987)."""
    m = _DATE_RE_ISO.match(value)
    if m:
        y, mo, d = m.groups()
    else:
        m = _DATE_RE_FR.match(value)
        if m:
            d, mo, y = m.groups()
        else:
            m = _DATE_RE_FR_YY.match(value)
            if not m:
                return value
            d, mo, y = m.groups()
            y = str((2000 if int(y) < 50 else 1900) + int(y))
    try:
        return date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return value


class Command(BaseCommand):
    help = "Réécrit les dates texte non ISO ('dd/mm/yyyy', 'dd/mm/yy', 'yyyy/mm/dd'…) en 'YYYY-MM-DD'."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche seulement le bilan.")
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--fields", type=str, default="DATEREV,DATOUV",
                            help="Champs à normaliser, séparés par des virgules (défaut : DATEREV,DATOUV).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        fields = [f.strip() for f in options["fields"].split(",") if f.strip()]
        iso_ok = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        for model in (Kyc_pp, Kyc_pm):
            model_fields = {f.name for f in model._meta.get_fields()}
            for field in fields:
                if field not in model_fields:
                    continue
                label = f"{model.__name__}.{field}"
                qs = model.objects.exclude(**{field: ""}).exclude(**{f"{field}__isnull": True})
                changed = unparsed = 0
                patterns = Counter()
                batch = []
                for pk, raw in qs.values_list("pk", field).iterator(chunk_size=10000):
                    if iso_ok.match(raw):
                        continue
                    new = normalize_date_text(raw.strip())
                    if new == raw or not iso_ok.match(new):
                        unparsed += 1
                        patterns[re.sub(r"\d", "9", raw)] += 1
                        if unparsed <= 10:
                            self.stdout.write(f"  {label} pk={pk} non reconnu : {raw!r}")
                        continue
                    changed += 1
                    if not dry_run:
                        batch.append(model(pk=pk, **{field: new}))
                        if len(batch) >= batch_size:
                            with transaction.atomic():
                                model.objects.bulk_update(batch, [field])
                            batch = []
                if batch:
                    with transaction.atomic():
                        model.objects.bulk_update(batch, [field])
                action = "à corriger" if dry_run else "corrigées"
                self.stdout.write(self.style.SUCCESS(
                    f"{label} : {changed} {action}, {unparsed} non reconnues (laissées telles quelles)."))
                if patterns:
                    self.stdout.write(f"  Formats non reconnus les plus fréquents ({label}) :")
                    for pat, count in patterns.most_common(10):
                        self.stdout.write(f"    {pat!r} x {count}")
        if not dry_run:
            try:
                from django.core.cache import cache
                cache.clear()
                self.stdout.write("Cache Django vidé.")
            except Exception:
                pass
