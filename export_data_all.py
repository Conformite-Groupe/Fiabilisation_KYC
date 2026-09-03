"""Export combine des donnees de la plateforme KYC.

Remplace a lui seul export_users.py, export_expl.py, export_data.py et
export_data_kyc.py. Produit un repertoire contenant :

    manifest_data_all.json   inventaire, comptes, options de l'export
    users.json               profils ProfileV + groupes + permissions
    codes_expl.json          username / email / code_expl
    data.json                TauxEvolution, TauxEvolution_filiale, Devise,
                             Notation (agent et note_par en cle naturelle)
    kyc_pp.jsonl(.gz)        table Kyc_pp, une ligne = un tableau de valeurs
    kyc_pm.jsonl(.gz)        table Kyc_pm, idem

Les identifiants techniques ne sont pas exportes : les objets sont reconnus
par cle naturelle a l'import (username, email, code expl). C'est ce qui permet
de charger des donnees de production dans une base de test qui possede deja
ses propres profils. Seules Kyc_pp et Kyc_pm conservent leur id.

Exemples
--------
    python export_data_all.py
    python export_data_all.py --output C:\\exports\\prod --gzip
    python export_data_all.py --sections users expl
    python export_data_all.py --sections kyc --filiale SN --limit 100000
    python export_data_all.py --database prod --gzip
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

FORMAT_VERSION = 1
SECTIONS = ["users", "expl", "data", "kyc"]
KYC_TABLES = {"pp": "kyc.Kyc_pp", "pm": "kyc.Kyc_pm"}
DATA_MODELS = {
    "taux_evolution": "kyc.TauxEvolution",
    "taux_evolution_filiale": "kyc.TauxEvolution_filiale",
    "devise": "kyc.Devise",
}
PROGRESS_STEP = 100000


def encode(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def serialiser(obj, exclus=()):
    return {f.attname: encode(getattr(obj, f.attname))
            for f in obj._meta.concrete_fields if f.attname not in exclus}


def ident_utilisateur(user):
    if user is None:
        return None
    return {
        "username": getattr(user, "username", None),
        "email": getattr(user, "email", None),
        "expl": getattr(user, "code_expl", None) or getattr(user, "expl", None),
    }


def export_users(out_dir, using):
    model = django_apps.get_model("accounts.ProfileV")
    lignes = []
    qs = model._default_manager.using(using).prefetch_related("groups", "user_permissions")
    for profil in qs:
        data = serialiser(profil, exclus=("id",))
        data["groups"] = list(profil.groups.values_list("name", flat=True))
        data["user_permissions"] = [
            f"{app}.{codename}" for app, codename in
            profil.user_permissions.values_list("content_type__app_label", "codename")
        ]
        lignes.append(data)

    chemin = os.path.join(out_dir, "users.json")
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(lignes, fh, ensure_ascii=False, indent=2)
    return {"section": "users", "file": "users.json", "count": len(lignes)}


def export_expl(out_dir, using):
    model = django_apps.get_model("accounts.ProfileV")
    lignes = [
        {"username": p.username, "email": p.email, "code_expl": (p.code_expl or "").strip()}
        for p in model._default_manager.using(using).all()
    ]
    chemin = os.path.join(out_dir, "codes_expl.json")
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(lignes, fh, ensure_ascii=False, indent=2)
    avec_code = sum(1 for l in lignes if l["code_expl"])
    return {"section": "expl", "file": "codes_expl.json", "count": len(lignes),
            "avec_code": avec_code}


def export_data(out_dir, using):
    export = {}
    detail = {}
    for cle, label in DATA_MODELS.items():
        model = django_apps.get_model(label)
        export[cle] = [serialiser(o, exclus=("id",))
                       for o in model._default_manager.using(using).all()]
        detail[cle] = len(export[cle])

    notation = django_apps.get_model("kyc.Notation")
    export["notation"] = []
    for n in notation._default_manager.using(using).select_related("agent", "note_par"):
        data = serialiser(n, exclus=("id", "agent_id", "note_par_id"))
        data["agent_ident"] = ident_utilisateur(n.agent)
        data["note_par_ident"] = ident_utilisateur(n.note_par)
        export["notation"].append(data)
    detail["notation"] = len(export["notation"])

    chemin = os.path.join(out_dir, "data.json")
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(export, fh, ensure_ascii=False, indent=2)
    return {"section": "data", "file": "data.json", "detail": detail,
            "count": sum(detail.values())}


def open_out(path, use_gzip):
    if use_gzip:
        return gzip.open(path + ".gz", "wt", encoding="utf-8", newline="\n")
    return open(path, "w", encoding="utf-8", newline="\n")


def export_kyc(scope, out_dir, using, filiales, limit, chunk, use_gzip):
    model = django_apps.get_model(KYC_TABLES[scope])
    columns = [f.attname for f in model._meta.concrete_fields]

    qs = model._default_manager.using(using).order_by("pk")
    if filiales:
        qs = qs.filter(FILIALE__in=filiales)
    if limit:
        qs = qs[:limit]

    filename = f"kyc_{scope}.jsonl"
    chemin = os.path.join(out_dir, filename)
    count = 0
    with open_out(chemin, use_gzip) as fh:
        for row in qs.values_list(*columns).iterator(chunk_size=chunk):
            fh.write(json.dumps([encode(v) for v in row], ensure_ascii=False) + "\n")
            count += 1
            if count % PROGRESS_STEP == 0:
                print(f"    {count} lignes...", flush=True)

    return {"section": "kyc", "scope": scope, "model": KYC_TABLES[scope],
            "table": model._meta.db_table, "file": filename + (".gz" if use_gzip else ""),
            "columns": columns, "count": count}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export combine des donnees KYC.")
    parser.add_argument("--output", "-o", default=None,
                        help="Repertoire de sortie (defaut : data_all_AAAAMMJJ_HHMM).")
    parser.add_argument("--database", "-d", default="default",
                        help="Alias de base defini dans settings.DATABASES.")
    parser.add_argument("--sections", nargs="*", choices=SECTIONS, default=SECTIONS,
                        help=f"Sections a exporter (defaut : {' '.join(SECTIONS)}).")
    parser.add_argument("--filiale", nargs="*", default=None,
                        help="Limiter Kyc_pp / Kyc_pm a ces filiales.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Nombre maximum de lignes par table KYC (tests).")
    parser.add_argument("--chunk", type=int, default=10000,
                        help="Taille des lots de lecture KYC (defaut 10000).")
    parser.add_argument("--gzip", action="store_true",
                        help="Compresser les fichiers KYC en .gz.")
    args = parser.parse_args(argv)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = args.output or f"data_all_{stamp}"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Base source   : {args.database}")
    print(f"Destination   : {os.path.abspath(out_dir)}")
    print(f"Sections      : {', '.join(args.sections)}")
    if args.filiale:
        print(f"Filiales      : {', '.join(args.filiale)}")
    if args.limit:
        print(f"Limite KYC    : {args.limit} lignes par table")
    print()

    entrees = []

    if "users" in args.sections:
        entree = export_users(out_dir, args.database)
        entrees.append(entree)
        print(f"  users                    {entree['count']:>10} profils")

    if "expl" in args.sections:
        entree = export_expl(out_dir, args.database)
        entrees.append(entree)
        print(f"  codes expl               {entree['count']:>10} profils, "
              f"{entree['avec_code']} avec un code")

    if "data" in args.sections:
        entree = export_data(out_dir, args.database)
        entrees.append(entree)
        for cle, nombre in entree["detail"].items():
            print(f"  {cle:<24} {nombre:>10} lignes")

    if "kyc" in args.sections:
        for scope in ("pp", "pm"):
            print(f"  {KYC_TABLES[scope]}")
            entree = export_kyc(scope, out_dir, args.database, args.filiale,
                                args.limit, args.chunk, args.gzip)
            entrees.append(entree)
            taille = os.path.getsize(os.path.join(out_dir, entree["file"])) / 1048576
            print(f"    {entree['count']} lignes, {taille:.1f} Mo")

    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "database": args.database,
        "sections": args.sections,
        "gzip": args.gzip,
        "filiales": args.filiale,
        "limit": args.limit,
        "django_version": django.get_version(),
        "total_rows": sum(e["count"] for e in entrees),
        "entries": entrees,
    }
    chemin = os.path.join(out_dir, "manifest_data_all.json")
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"\nTotal : {manifest['total_rows']} lignes.")
    print(f"Manifest : {chemin}")
    connections.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
