import argparse
import json
import os
import sys
from datetime import datetime

import django


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import DataQualityRule


DEFAULT_OUTPUT = "quality_rules_export.json"


def build_queryset(args):
    queryset = (
        DataQualityRule.objects
        .prefetch_related("conditions")
        .order_by("id")
    )

    if args.active_only:
        queryset = queryset.filter(active=True)
    if args.applicability:
        queryset = queryset.filter(applicability=args.applicability)
    if args.filiale:
        queryset = queryset.filter(filiale__icontains=f"|{args.filiale}|")

    return queryset


def serialize_rule(rule):
    return {
        "name": rule.name,
        "applicability": rule.applicability,
        "field_name": rule.field_name,
        "control_type": rule.control_type,
        "parameter": rule.parameter or "",
        "description": rule.description or "",
        "active": rule.active,
        "filiale": rule.filiale or "",
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "conditions": [
            {
                "logic": condition.logic,
                "field_name": condition.field_name,
                "operator": condition.operator,
                "value": condition.value or "",
            }
            for condition in rule.conditions.all()
        ],
    }


def export_rules(args):
    rules = [serialize_rule(rule) for rule in build_queryset(args)]
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "format": "kyc_data_quality_rules_v1",
        "count": len(rules),
        "rules": rules,
    }

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"Export terminé : {len(rules)} règle(s) exportée(s) vers {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exporte les règles de contrôle qualité KYC avec leurs conditions."
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Fichier JSON de sortie. Défaut : {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Exporter uniquement les règles actives.",
    )
    parser.add_argument(
        "--applicability",
        choices=["PP", "PM"],
        help="Limiter l'export aux règles PP ou PM.",
    )
    parser.add_argument(
        "--filiale",
        help="Limiter l'export à une filiale, par exemple 'BOA SN'.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    export_rules(parse_args())
