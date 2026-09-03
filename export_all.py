"""Export complet des donnees de la plateforme KYC.

Exporte tous les modeles des applications choisies (par defaut : accounts + kyc,
donc ProfileV, Kyc_pp, Kyc_pm, Notation, TauxEvolution, DataQualityRule,
KycDocumentExtraction, AuditEvent, etc.) au format JSON Lines (une ligne = un
enregistrement), un fichier par modele, plus un manifest.json qui fixe l'ordre
de rechargement (dependances de cles etrangeres).

Les cles primaires sont conservees : les FK restent valides a l'import sans
aucune resolution par cle naturelle.

Exemples
--------
    python export_all.py
    python export_all.py --output C:\\exports\\kyc_20260805 --gzip
    python export_all.py --database prod --apps kyc accounts --with-auth
    python export_all.py --models kyc.Kyc_pp kyc.Kyc_pm
    python export_all.py --exclude kyc.KycDocumentExtraction --chunk 5000
"""

import argparse
import datetime
import decimal
import gzip
import json
import os
import sys
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")

import django

django.setup()

from django.apps import apps as django_apps
from django.db import connections

DEFAULT_APPS = ["accounts", "kyc"]

AUTH_MODELS = ["auth.Group", "auth.Permission", "contenttypes.ContentType"]
FORMAT_VERSION = 1


def encode_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        import base64
        return {"__bytes__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def m2m_natural_key(field, related_obj):
    label = field.related_model._meta.label
    if label == "auth.Group":
        return related_obj.name
    if label == "auth.Permission":
        return f"{related_obj.content_type.app_label}.{related_obj.codename}"
    if label == "contenttypes.ContentType":
        return f"{related_obj.app_label}.{related_obj.model}"
    return related_obj.pk


def sort_models(models):
    remaining = list(models)
    selected = {m._meta.label for m in remaining}
    ordered, placed = [], set()

    while remaining:
        progress = False
        for model in list(remaining):
            deps = set()
            for f in model._meta.get_fields():
                if not (f.many_to_one or f.one_to_one) or not getattr(f, "concrete", False):
                    continue
                target = f.related_model._meta.label
                if target != model._meta.label and target in selected:
                    deps.add(target)
            if deps <= placed:
                ordered.append(model)
                placed.add(model._meta.label)
                remaining.remove(model)
                progress = True
        if not progress:

            for model in remaining:
                ordered.append(model)
                placed.add(model._meta.label)
            break
    return ordered


def collect_models(app_labels, with_auth, only, exclude):
    if only:
        wanted = [django_apps.get_model(label) for label in only]
        return sort_models(wanted)

    models = []
    for app_label in app_labels:
        config = django_apps.get_app_config(app_label)
        models.extend(config.get_models())
    if with_auth:
        models.extend(django_apps.get_model(label) for label in AUTH_MODELS)


    models = [m for m in models if not m._meta.proxy and not m._meta.auto_created]

    excluded = {e.lower() for e in (exclude or [])}
    models = [m for m in models if m._meta.label.lower() not in excluded]
    return sort_models(models)


def open_out(path, use_gzip):
    if use_gzip:
        return gzip.open(path + ".gz", "wt", encoding="utf-8", newline="\n")
    return open(path, "w", encoding="utf-8", newline="\n")


def export_model(model, out_dir, using, chunk, use_gzip):
    meta = model._meta
    concrete = [f for f in meta.concrete_fields]
    m2m = [f for f in meta.many_to_many]

    filename = f"{meta.label}.jsonl"
    path = os.path.join(out_dir, filename)

    qs = model._default_manager.using(using).order_by("pk")
    if m2m:
        qs = qs.prefetch_related(*[f.name for f in m2m])

    count = 0
    with open_out(path, use_gzip) as fh:
        for obj in qs.iterator(chunk_size=chunk):
            row = {}
            for f in concrete:
                row[f.attname] = encode_value(f.value_from_object(obj))
            if m2m:
                links = {}
                for f in m2m:
                    links[f.name] = [
                        m2m_natural_key(f, rel) for rel in getattr(obj, f.name).all()
                    ]
                row["__m2m__"] = links
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    return {
        "model": meta.label,
        "file": filename + (".gz" if use_gzip else ""),
        "count": count,
        "pk_field": meta.pk.attname,
        "fields": [f.attname for f in concrete],
        "m2m": [f.name for f in m2m],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export complet des donnees KYC (JSON Lines).")
    parser.add_argument("--output", "-o", default=None,
                        help="Repertoire de sortie (defaut : export_kyc_AAAAMMJJ_HHMM).")
    parser.add_argument("--database", "-d", default="default",
                        help="Alias de base defini dans settings.DATABASES (default, prod...).")
    parser.add_argument("--apps", nargs="*", default=DEFAULT_APPS,
                        help=f"Applications a exporter (defaut : {' '.join(DEFAULT_APPS)}).")
    parser.add_argument("--models", nargs="*", default=None,
                        help="Limiter a ces modeles (ex. kyc.Kyc_pp accounts.ProfileV).")
    parser.add_argument("--exclude", nargs="*", default=None,
                        help="Modeles a ignorer (ex. kyc.KycDocumentExtraction).")
    parser.add_argument("--with-auth", action="store_true",
                        help="Inclure auth.Group / auth.Permission / contenttypes.ContentType.")
    parser.add_argument("--chunk", type=int, default=2000,
                        help="Taille des lots de lecture (defaut 2000).")
    parser.add_argument("--gzip", action="store_true", help="Compresser chaque fichier en .gz.")
    args = parser.parse_args(argv)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = args.output or f"export_kyc_{stamp}"
    os.makedirs(out_dir, exist_ok=True)

    models = collect_models(args.apps, args.with_auth, args.models, args.exclude)
    if not models:
        print("Aucun modele a exporter.")
        return 1

    print(f"Base source   : {args.database}")
    print(f"Destination   : {os.path.abspath(out_dir)}")
    print(f"Modeles       : {len(models)}\n")

    entries, total = [], 0
    for model in models:
        entry = export_model(model, out_dir, args.database, args.chunk, args.gzip)
        entries.append(entry)
        total += entry["count"]
        print(f"  {entry['model']:<45} {entry['count']:>10} lignes")

    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "database": args.database,
        "gzip": args.gzip,
        "django_version": django.get_version(),
        "total_rows": total,

        "models": entries,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"\nTotal : {total} lignes dans {len(entries)} fichiers.")
    print(f"Manifest : {os.path.join(out_dir, 'manifest.json')}")
    connections.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
