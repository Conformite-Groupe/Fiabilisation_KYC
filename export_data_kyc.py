"""Export des donnees KYC clients : Kyc_pp et Kyc_pm.

Ecrit un fichier JSON Lines par table (une ligne = un tableau de valeurs, dans
l'ordre des colonnes donne par le manifest) plus un manifest_kyc_data.json.

Lecture en flux, sans instancier d'objets Django : tient sur les tables de
plusieurs millions de lignes sans saturer la memoire.

Exemples
--------
    python export_data_kyc.py
    python export_data_kyc.py --output C:\\exports\\kyc_data --gzip
    python export_data_kyc.py --scope pp --filiale SN ML
    python export_data_kyc.py --database prod --gzip --chunk 20000
"""

import argparse
import datetime
import gzip
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")

import django

django.setup()

from django.apps import apps as django_apps
from django.db import connections

FORMAT_VERSION = 1
TABLES = {"pp": "kyc.Kyc_pp", "pm": "kyc.Kyc_pm"}
PROGRESS_STEP = 100000


def open_out(path, use_gzip):
    if use_gzip:
        return gzip.open(path + ".gz", "wt", encoding="utf-8", newline="\n")
    return open(path, "w", encoding="utf-8", newline="\n")


def encode(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


def export_table(scope, out_dir, using, filiales, chunk, use_gzip, limit):
    model = django_apps.get_model(TABLES[scope])
    columns = [f.attname for f in model._meta.concrete_fields]

    qs = model._default_manager.using(using).order_by("pk")
    if filiales:
        qs = qs.filter(FILIALE__in=filiales)
    if limit:
        qs = qs[:limit]

    filename = f"kyc_{scope}.jsonl"
    path = os.path.join(out_dir, filename)

    count = 0
    with open_out(path, use_gzip) as fh:
        for row in qs.values_list(*columns).iterator(chunk_size=chunk):
            fh.write(json.dumps([encode(v) for v in row], ensure_ascii=False) + "\n")
            count += 1
            if count % PROGRESS_STEP == 0:
                print(f"    {count} lignes...", flush=True)

    return {"scope": scope, "model": TABLES[scope], "file": filename + (".gz" if use_gzip else ""),
            "table": model._meta.db_table, "columns": columns, "count": count}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export des donnees KYC (Kyc_pp / Kyc_pm).")
    parser.add_argument("--output", "-o", default=None,
                        help="Repertoire de sortie (defaut : kyc_data_AAAAMMJJ_HHMM).")
    parser.add_argument("--database", "-d", default="default",
                        help="Alias de base defini dans settings.DATABASES.")
    parser.add_argument("--scope", choices=["pp", "pm", "both"], default="both",
                        help="Table(s) a exporter (defaut : both).")
    parser.add_argument("--filiale", nargs="*", default=None,
                        help="Limiter a ces filiales (ex. SN ML BF).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Nombre maximum de lignes par table (tests).")
    parser.add_argument("--chunk", type=int, default=10000,
                        help="Taille des lots de lecture (defaut 10000).")
    parser.add_argument("--gzip", action="store_true", help="Compresser les fichiers en .gz.")
    args = parser.parse_args(argv)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = args.output or f"kyc_data_{stamp}"
    os.makedirs(out_dir, exist_ok=True)

    scopes = ["pp", "pm"] if args.scope == "both" else [args.scope]

    print(f"Base source   : {args.database}")
    print(f"Destination   : {os.path.abspath(out_dir)}")
    print(f"Tables        : {', '.join(TABLES[s] for s in scopes)}")
    if args.filiale:
        print(f"Filiales      : {', '.join(args.filiale)}")
    if args.limit:
        print(f"Limite        : {args.limit} lignes par table")
    print()

    entries, total = [], 0
    for scope in scopes:
        print(f"  {TABLES[scope]}")
        entry = export_table(scope, out_dir, args.database, args.filiale,
                             args.chunk, args.gzip, args.limit)
        entries.append(entry)
        total += entry["count"]
        taille = os.path.getsize(os.path.join(out_dir, entry["file"]))
        print(f"    {entry['count']} lignes, {taille / 1048576:.1f} Mo\n")

    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "database": args.database,
        "gzip": args.gzip,
        "filiales": args.filiale,
        "limit": args.limit,
        "django_version": django.get_version(),
        "total_rows": total,
        "tables": entries,
    }
    manifest_path = os.path.join(out_dir, "manifest_kyc_data.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"Total : {total} lignes.")
    print(f"Manifest : {manifest_path}")
    connections.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
