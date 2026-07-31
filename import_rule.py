import argparse
import json
import os
import sys

import django
from django.db import transaction


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import DataQualityCondition, DataQualityRule


DEFAULT_INPUT = "quality_rules_export.json"


def load_payload(path):
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        return {"rules": payload}
    if not isinstance(payload, dict) or "rules" not in payload:
        raise ValueError("Format invalide : le fichier doit contenir une clé 'rules'.")
    if not isinstance(payload["rules"], list):
        raise ValueError("Format invalide : 'rules' doit être une liste.")
    return payload


def clean_text(value):
    return "" if value is None else str(value)


def import_rules(args):
    input_path = os.path.abspath(args.input)
    payload = load_payload(input_path)

    created = 0
    updated = 0
    skipped = 0
    condition_count = 0

    with transaction.atomic():
        for index, item in enumerate(payload["rules"], start=1):
            name = clean_text(item.get("name")).strip()
            applicability = clean_text(item.get("applicability")).strip()
            filiale = clean_text(item.get("filiale"))

            if not name or not applicability:
                skipped += 1
                print(f"[SKIP] Ligne {index} : name/applicability manquant.")
                continue

            lookup = {
                "name": name,
                "applicability": applicability,
                "filiale": filiale,
            }
            defaults = {
                "field_name": clean_text(item.get("field_name")),
                "control_type": clean_text(item.get("control_type")) or "composite",
                "parameter": clean_text(item.get("parameter")),
                "description": clean_text(item.get("description")),
                "active": bool(item.get("active", True)),
            }

            if args.dry_run:
                exists = DataQualityRule.objects.filter(**lookup).exists()
                updated += int(exists)
                created += int(not exists)
                condition_count += len(item.get("conditions") or [])
                continue

            rule, is_created = DataQualityRule.objects.update_or_create(
                **lookup,
                defaults=defaults,
            )

            rule.conditions.all().delete()
            conditions = []
            for condition in item.get("conditions") or []:
                conditions.append(DataQualityCondition(
                    rule=rule,
                    logic=clean_text(condition.get("logic")) or "AND",
                    field_name=clean_text(condition.get("field_name")),
                    operator=clean_text(condition.get("operator")),
                    value=clean_text(condition.get("value")),
                ))
            DataQualityCondition.objects.bulk_create(conditions)

            created += int(is_created)
            updated += int(not is_created)
            condition_count += len(conditions)
            print(f"[{'NEW' if is_created else 'UPD'}] {rule.name} [{rule.applicability}] {rule.filiale}")

        if args.dry_run:
            transaction.set_rollback(True)

    mode = "Simulation" if args.dry_run else "Import"
    print(
        f"{mode} terminé : {created} création(s), {updated} mise(s) à jour, "
        f"{skipped} ignorée(s), {condition_count} condition(s)."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Importe les règles de contrôle qualité KYC avec leurs conditions."
    )
    parser.add_argument(
        "-i", "--input",
        default=DEFAULT_INPUT,
        help=f"Fichier JSON à importer. Défaut : {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simuler l'import sans écrire en base.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    import_rules(parse_args())
