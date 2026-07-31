import argparse
import json
import os
import sys

import django
from django.core.cache import cache
from django.db import transaction


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import TermTranslation


DEFAULT_INPUT = "glossary_export.json"


def load_payload(path):
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        return {"terms": payload}
    if not isinstance(payload, dict) or "terms" not in payload:
        raise ValueError("Format invalide : le fichier doit contenir une clé 'terms'.")
    if not isinstance(payload["terms"], list):
        raise ValueError("Format invalide : 'terms' doit être une liste.")
    return payload


def clean_text(value):
    return "" if value is None else str(value)


def import_glossary(args):
    input_path = os.path.abspath(args.input)
    payload = load_payload(input_path)

    created = 0
    updated = 0
    kept = 0
    skipped = 0

    with transaction.atomic():
        for index, item in enumerate(payload["terms"], start=1):
            terme_fr = clean_text(item.get("terme_fr")).strip()
            terme_en = clean_text(item.get("terme_en")).strip()
            note = clean_text(item.get("note"))

            if not terme_fr or not terme_en:
                skipped += 1
                print(f"[SKIP] Ligne {index} : terme_fr/terme_en manquant.")
                continue

            existing = TermTranslation.objects.filter(terme_fr=terme_fr).first()

            if args.dry_run:
                if existing and args.keep_existing:
                    kept += 1
                elif existing:
                    updated += 1
                else:
                    created += 1
                continue

            if existing:
                if args.keep_existing:
                    kept += 1
                    print(f"[KEEP] {terme_fr}")
                    continue
                existing.terme_en = terme_en
                existing.note = note
                existing.save(update_fields=["terme_en", "note", "updated_at"])
                updated += 1
                print(f"[UPD] {terme_fr}")
            else:
                TermTranslation.objects.create(
                    terme_fr=terme_fr,
                    terme_en=terme_en,
                    note=note,
                )
                created += 1
                print(f"[NEW] {terme_fr}")

        if args.dry_run:
            transaction.set_rollback(True)

    if not args.dry_run:
        cache.delete("term_glossary_en")

    mode = "Simulation" if args.dry_run else "Import"
    print(
        f"{mode} terminé : {created} création(s), {updated} mise(s) à jour, "
        f"{kept} conservé(s), {skipped} ignoré(s)."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Importe le glossaire de traduction français -> anglais."
    )
    parser.add_argument(
        "-i", "--input",
        default=DEFAULT_INPUT,
        help=f"Fichier JSON à importer. Défaut : {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Ne pas écraser les traductions déjà présentes en base.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simuler l'import sans écrire en base.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    import_glossary(parse_args())
