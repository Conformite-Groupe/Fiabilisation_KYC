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

from kyc.models import TermTranslation


DEFAULT_OUTPUT = "glossary_export.json"


def build_queryset(args):
    queryset = TermTranslation.objects.all().order_by("terme_fr")

    if args.search:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(terme_fr__icontains=args.search)
            | Q(terme_en__icontains=args.search)
            | Q(note__icontains=args.search)
        )

    return queryset


def serialize_term(term):
    return {
        "terme_fr": term.terme_fr,
        "terme_en": term.terme_en,
        "note": term.note or "",
        "updated_at": term.updated_at.isoformat() if term.updated_at else None,
    }


def export_glossary(args):
    terms = [serialize_term(term) for term in build_queryset(args)]
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "format": "kyc_glossary_fr_en_v1",
        "count": len(terms),
        "terms": terms,
    }

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"Export terminé : {len(terms)} terme(s) exporté(s) vers {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exporte le glossaire de traduction français -> anglais."
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Fichier JSON de sortie. Défaut : {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--search",
        help="Limiter l'export aux termes contenant ce texte en FR, EN ou note.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    export_glossary(parse_args())
