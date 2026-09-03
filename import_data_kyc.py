"""Import des donnees KYC clients : Kyc_pp et Kyc_pm.

Recharge un repertoire produit par export_data_kyc.py. Insertion en SQL brut
(executemany), sans instancier d'objets Django : c'est le chemin le plus rapide
pour les tables de plusieurs millions de lignes.

Les colonnes sont appariees par nom entre le manifest et le schema de la base
cible : une colonne absente d'un cote est signalee, jamais devinee.

Par defaut le script n'ecrit rien sans mode explicite :

    --flush       vide la table avant rechargement (DESTRUCTIF)
    --append      insere sans rien supprimer

Exemples
--------
    python import_data_kyc.py kyc_data_20260805_1930 --flush
    python import_data_kyc.py kyc_data_20260805_1930 --append --scope pp
    python import_data_kyc.py kyc_data_20260805_1930 --flush --dry-run
    python import_data_kyc.py kyc_data_20260805_1930 --flush --database prod --yes
"""

import argparse
import gzip
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")

import django

django.setup()

from django.apps import apps as django_apps
from django.core.management.color import no_style
from django.db import IntegrityError, connections, transaction

PROGRESS_STEP = 100000


def open_in(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def read_rows(path):
    with open_in(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def align_columns(entry, model):
    source = entry["columns"]
    cible = {f.attname: f for f in model._meta.concrete_fields}

    gardees, positions, defauts = [], [], []
    for name, field in cible.items():
        if name in source:
            gardees.append(name)
            positions.append(source.index(name))
            defauts.append(None)
        else:
            gardees.append(name)
            positions.append(None)
            defauts.append(None if field.null else "")

    manquantes = [n for n, p in zip(gardees, positions) if p is None]
    surplus = [n for n in source if n not in cible]
    return gardees, positions, defauts, manquantes, surplus


def import_table(entry, base_dir, using, batch_size, mode, dry_run):
    model = django_apps.get_model(entry["model"])
    path = os.path.join(base_dir, entry["file"])
    if not os.path.exists(path):
        return {"model": entry["model"], "inserted": 0, "missing_file": True,
                "manquantes": [], "surplus": []}

    colonnes, positions, defauts, manquantes, surplus = align_columns(entry, model)
    connection = connections[using]
    table = connection.ops.quote_name(model._meta.db_table)
    noms = ", ".join(connection.ops.quote_name(c) for c in colonnes)
    place = ", ".join(["%s"] * len(colonnes))
    sql = f"INSERT INTO {table} ({noms}) VALUES ({place})"

    inserted = 0
    lot = []

    def flush(cursor):
        nonlocal inserted
        if not lot:
            return
        if not dry_run:
            cursor.executemany(sql, lot)
        inserted += len(lot)
        lot.clear()
        if inserted % PROGRESS_STEP < batch_size:
            print(f"    {inserted} lignes...", flush=True)

    with connection.cursor() as cursor:
        for row in read_rows(path):
            lot.append(tuple(row[p] if p is not None else d
                             for p, d in zip(positions, defauts)))
            if len(lot) >= batch_size:
                flush(cursor)
        flush(cursor)

    return {"model": entry["model"], "inserted": inserted, "missing_file": False,
            "manquantes": manquantes, "surplus": surplus}


def truncate(entries, using):
    connection = connections[using]
    with connection.cursor() as cursor:
        for entry in entries:
            model = django_apps.get_model(entry["model"])
            table = connection.ops.quote_name(model._meta.db_table)
            cursor.execute(f"DELETE FROM {table}")
            print(f"  vide : {model._meta.db_table}")


def reset_sequences(entries, using):
    connection = connections[using]
    models = [django_apps.get_model(e["model"]) for e in entries]
    statements = connection.ops.sequence_reset_sql(no_style(), models)
    if not statements:
        return
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import des donnees KYC (Kyc_pp / Kyc_pm).")
    parser.add_argument("source", help="Repertoire produit par export_data_kyc.py.")
    parser.add_argument("--database", "-d", default="default",
                        help="Alias de base cible defini dans settings.DATABASES.")
    parser.add_argument("--scope", choices=["pp", "pm", "both"], default="both",
                        help="Table(s) a importer (defaut : both).")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--flush", action="store_true",
                       help="DESTRUCTIF : vide la table avant rechargement.")
    group.add_argument("--append", action="store_true",
                       help="Insere sans rien supprimer.")

    parser.add_argument("--batch", type=int, default=5000,
                        help="Taille des lots d'insertion (defaut 5000).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule : lit les fichiers et compte, sans ecrire.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Ne pas demander de confirmation.")
    args = parser.parse_args(argv)

    manifest_path = os.path.join(args.source, "manifest_kyc_data.json")
    if not os.path.exists(manifest_path):
        print(f"manifest_kyc_data.json introuvable dans {args.source}")
        return 1
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    entries = manifest["tables"]
    if args.scope != "both":
        entries = [e for e in entries if e["scope"] == args.scope]
    if not entries:
        print("Aucune table a importer.")
        return 1

    mode = "flush" if args.flush else "append"
    attendues = sum(e["count"] for e in entries)

    print(f"Source        : {os.path.abspath(args.source)}")
    print(f"Export du     : {manifest.get('exported_at')} (base {manifest.get('database')})")
    print(f"Base cible    : {args.database}")
    print(f"Mode          : {mode}{'  [DRY-RUN]' if args.dry_run else ''}")
    print(f"Tables        : {', '.join(e['model'] for e in entries)}")
    if manifest.get("filiales"):
        print(f"Filiales      : {', '.join(manifest['filiales'])}")
    print(f"Lignes        : {attendues} attendues\n")

    if mode == "flush" and not args.dry_run and not args.yes:
        reponse = input(f"Vider puis recharger {len(entries)} tables de la base "
                        f"'{args.database}' ? Tapez OUI pour continuer : ")
        if reponse.strip().upper() != "OUI":
            print("Annule.")
            return 1

    results = []
    with transaction.atomic(using=args.database):
        if mode == "flush" and not args.dry_run:
            print("Purge des tables :")
            truncate(entries, args.database)
            print()

        for entry in entries:
            print(f"  {entry['model']}")
            try:
                res = import_table(entry, args.source, args.database,
                                   args.batch, mode, args.dry_run)
            except IntegrityError as exc:
                transaction.set_rollback(True, using=args.database)
                print(f"\n  ECHEC sur {entry['model']} : {exc}")
                print("\nAucune ecriture conservee : la transaction a ete annulee.")
                print("En mode --append, des identifiants de l'export existent")
                print("deja dans la table cible : utilisez --flush.")
                return 1
            results.append(res)
            if res["missing_file"]:
                print(f"    FICHIER ABSENT ({entry['file']})")
                continue
            print(f"    {res['inserted']} lignes inserees")
            if res["manquantes"]:
                print(f"    colonnes absentes de l'export, remplies a vide : "
                      f"{', '.join(res['manquantes'])}")
            if res["surplus"]:
                print(f"    colonnes de l'export inconnues ici, ignorees : "
                      f"{', '.join(res['surplus'])}")

        if not args.dry_run:
            reset_sequences(entries, args.database)

        if args.dry_run:
            transaction.set_rollback(True, using=args.database)

    total = sum(r["inserted"] for r in results)
    print(f"\nTotal : {total} lignes {'simulees' if args.dry_run else 'importees'}.")
    if args.dry_run:
        print("Aucune ecriture effectuee (dry-run, transaction annulee).")
    connections.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
