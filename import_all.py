"""Import complet des donnees de la plateforme KYC.

Recharge un repertoire produit par export_all.py (manifest.json + fichiers
.jsonl / .jsonl.gz), dans l'ordre des dependances de cles etrangeres, en
conservant les cles primaires d'origine.

Par defaut le script NE TOUCHE A RIEN sans confirmation : il faut choisir
explicitement le mode d'ecriture.

    --append      insere les lignes telles quelles (echec si PK deja presente)
    --skip-existing  ignore les lignes dont la PK existe deja
    --flush       vide les tables concernees avant de recharger (RECOMMANDE
                  pour une restauration fidele, DESTRUCTIF)

Exemples
--------
    python import_all.py export_kyc_20260805_0930 --flush
    python import_all.py export_kyc_20260805_0930 --database prod --flush
    python import_all.py export_kyc_20260805_0930 --models kyc.Kyc_pp --flush
    python import_all.py export_kyc_20260805_0930 --skip-existing --batch 2000
    python import_all.py export_kyc_20260805_0930 --flush --dry-run

Si l'export vient d'une installation dont le code differe de celui-ci :

    --strict            echouer si un modele de l'export est inconnu ici
                        (par defaut ces modeles sont signales puis ignores)
    --exclude LABEL     laisser un modele de cote
    --ignore-conflicts  ecarter les lignes qui violent une contrainte d'unicite
                        absente du schema source (PERTE DE DONNEES)
"""

import argparse
import base64
import collections
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


def decode_value(field, value):
    if value is None:
        return None
    if isinstance(value, dict) and "__bytes__" in value:
        return base64.b64decode(value["__bytes__"])
    if field.is_relation:

        return value
    try:
        return field.to_python(value)
    except Exception:
        return value


def resolve_m2m_target(field, key, cache, using):
    label = field.related_model._meta.label
    store = cache.setdefault(label, {})
    if key in store:
        return store[key]

    model = field.related_model
    obj = None
    try:
        if label == "auth.Group":
            obj = model._default_manager.using(using).filter(name=key).first()
        elif label == "auth.Permission":
            app_label, codename = str(key).split(".", 1)
            obj = model._default_manager.using(using).filter(
                content_type__app_label=app_label, codename=codename).first()
        elif label == "contenttypes.ContentType":
            app_label, name = str(key).split(".", 1)
            obj = model._default_manager.using(using).filter(
                app_label=app_label, model=name).first()
        else:
            obj = model._default_manager.using(using).filter(pk=key).first()
    except ValueError:
        obj = None

    store[key] = obj.pk if obj else None
    return store[key]


def table_names(model):
    names = [model._meta.db_table]
    for f in model._meta.many_to_many:
        through = f.remote_field.through
        if through._meta.auto_created:
            names.append(through._meta.db_table)
    return names


def truncate(models, using, verbose=True):
    connection = connections[using]
    with connection.cursor() as cursor:
        for model in reversed(models):
            for table in reversed(table_names(model)):
                cursor.execute(f"DELETE FROM {connection.ops.quote_name(table)}")
                if verbose:
                    print(f"  vide : {table}")


def reset_sequences(models, using):
    connection = connections[using]
    statements = connection.ops.sequence_reset_sql(no_style(), models)
    if not statements:
        return
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def unique_keys(model):
    meta = model._meta
    keys = []
    for f in meta.concrete_fields:
        if f.unique and not f.primary_key:
            keys.append((f.attname,))
    for group in meta.unique_together:
        keys.append(tuple(meta.get_field(name).attname for name in group))
    for constraint in meta.constraints:
        fields = getattr(constraint, "fields", None)
        if fields:
            keys.append(tuple(meta.get_field(name).attname for name in fields))
    return keys


def diagnose_duplicates(entry, base_dir, model):
    path = os.path.join(base_dir, entry["file"])
    keys = unique_keys(model)
    if not keys or not os.path.exists(path):
        return []

    seen = {key: set() for key in keys}
    dupes = {key: 0 for key in keys}
    for row in read_rows(path):
        for key in keys:
            values = tuple(row.get(name) for name in key)
            if all(v in (None, "") for v in values):
                continue
            if values in seen[key]:
                dupes[key] += 1
            else:
                seen[key].add(values)
    return [(key, n) for key, n in dupes.items() if n]


def import_model(entry, base_dir, using, batch_size, mode, dry_run,
                 ignore_conflicts=False):
    model = django_apps.get_model(entry["model"])
    meta = model._meta
    path = os.path.join(base_dir, entry["file"])
    if not os.path.exists(path):
        return {"model": entry["model"], "created": 0, "skipped": 0, "rejected": 0,
                "unknown_fields": [], "m2m": [], "missing_file": True}

    fields = {f.attname: f for f in meta.concrete_fields}
    m2m_fields = {f.name: f for f in meta.many_to_many}

    existing = set()
    if mode == "skip-existing":
        existing = set(model._default_manager.using(using)
                       .values_list(meta.pk.attname, flat=True))

    before = None
    if ignore_conflicts and not dry_run:
        before = model._default_manager.using(using).count()

    unknown = set()
    created = skipped = 0
    buffer = []
    m2m_rows = []

    def flush_buffer():
        nonlocal created
        if not buffer:
            return
        if not dry_run:
            model._default_manager.using(using).bulk_create(
                buffer, batch_size=batch_size, ignore_conflicts=ignore_conflicts)
        created += len(buffer)
        buffer.clear()

    for row in read_rows(path):
        links = row.pop("__m2m__", None)
        pk_value = row.get(meta.pk.attname)
        if mode == "skip-existing" and pk_value in existing:
            skipped += 1
            continue

        obj = model()
        for key, raw in row.items():
            field = fields.get(key)
            if field is None:
                unknown.add(key)
                continue
            setattr(obj, field.attname, decode_value(field, raw))
        buffer.append(obj)

        if links:
            for name, keys in links.items():
                field = m2m_fields.get(name)
                if field is not None and keys:
                    m2m_rows.append((field, pk_value, keys))

        if len(buffer) >= batch_size:
            flush_buffer()
    flush_buffer()

    rejected = 0
    if before is not None:
        rejected = created - (model._default_manager.using(using).count() - before)

    return {"model": entry["model"], "created": created - rejected, "skipped": skipped,
            "rejected": rejected, "unknown_fields": sorted(unknown), "m2m": m2m_rows,
            "missing_file": False}


def report_integrity_error(entry, model, args, exc):
    label = entry["model"]
    print(f"\n  {label:<45} ECHEC : contrainte de la base violee")
    print(f"\n{exc}\n")
    print("Aucune ecriture conservee : la transaction a ete annulee,")
    print("la base est dans l'etat ou elle etait avant la commande.\n")

    dupes = diagnose_duplicates(entry, args.source, model)
    if dupes:
        print(f"L'export de {label} contient des doublons sur des colonnes que")
        print("le schema de cette base declare uniques :")
        for key, nombre in dupes:
            print(f"  - {' + '.join(key):<40} {nombre} lignes en doublon")
        print("\nLe schema source n'imposait pas cette unicite : les deux")
        print("installations ne sont pas a la meme version du code.\n")

    print("Options :")
    print(f"  --exclude {label}       importer tout le reste")
    print("  --ignore-conflicts        inserer ce qui passe, ecarter les lignes")
    print("                            en conflit (PERTE DE DONNEES silencieuse)")
    print("  aligner le code de cette installation puis 'manage.py migrate'")


def import_m2m(m2m_rows, using, batch_size, dry_run):
    cache = {}
    total = 0
    introuvables = collections.Counter()
    for field, source_pk, keys in m2m_rows:
        through = field.remote_field.through
        source_attr = field.m2m_column_name()
        target_attr = field.m2m_reverse_name()
        objs = []
        for key in keys:
            target_pk = resolve_m2m_target(field, key, cache, using)
            if target_pk is None:
                introuvables[(field.related_model._meta.label, key)] += 1
                continue
            objs.append(through(**{source_attr: source_pk, target_attr: target_pk}))
        if objs and not dry_run:
            through._default_manager.using(using).bulk_create(
                objs, batch_size=batch_size, ignore_conflicts=True)
        total += len(objs)
    return total, introuvables


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import complet des donnees KYC (JSON Lines).")
    parser.add_argument("source", help="Repertoire produit par export_all.py (contient manifest.json).")
    parser.add_argument("--database", "-d", default="default",
                        help="Alias de base cible defini dans settings.DATABASES.")
    parser.add_argument("--models", nargs="*", default=None,
                        help="Limiter a ces modeles (ex. kyc.Kyc_pp accounts.ProfileV).")
    parser.add_argument("--exclude", nargs="*", default=None, help="Modeles a ignorer.")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--flush", action="store_true",
                       help="DESTRUCTIF : vide les tables concernees avant rechargement.")
    group.add_argument("--append", action="store_true",
                       help="Insere sans rien supprimer (echec si une PK existe deja).")
    group.add_argument("--skip-existing", action="store_true",
                       help="Insere seulement les lignes dont la PK est absente.")

    parser.add_argument("--batch", type=int, default=1000, help="Taille des lots d'insertion.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule : lit les fichiers et compte, sans ecrire.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Ne pas demander de confirmation (mode non interactif).")
    parser.add_argument("--strict", action="store_true",
                        help="Echouer si l'export contient un modele absent de ce code.")
    parser.add_argument("--ignore-conflicts", action="store_true",
                        help="Ecarter les lignes qui violent une contrainte d'unicite "
                             "au lieu d'echouer (perte de donnees).")
    args = parser.parse_args(argv)

    manifest_path = os.path.join(args.source, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"manifest.json introuvable dans {args.source}")
        return 1
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    entries = manifest["models"]
    if args.models:
        wanted = {m.lower() for m in args.models}
        entries = [e for e in entries if e["model"].lower() in wanted]
    if args.exclude:
        skipped_labels = {m.lower() for m in args.exclude}
        entries = [e for e in entries if e["model"].lower() not in skipped_labels]
    if not entries:
        print("Aucun modele a importer.")
        return 1

    resolved, unknown = [], []
    for entry in entries:
        try:
            resolved.append((entry, django_apps.get_model(entry["model"])))
        except LookupError:
            unknown.append(entry)

    if unknown:
        print("ATTENTION : modeles presents dans l'export mais absents du code")
        print("de cette installation (versions differentes du projet) :")
        for entry in unknown:
            print(f"  - {entry['model']:<45} {entry['count']:>10} lignes NON importees")
        if args.strict:
            print("\nArret (--strict). Mettez le code a jour, ou relancez sans --strict.")
            return 1
        print()

    entries = [e for e, _ in resolved]
    models = [m for _, m in resolved]
    if not entries:
        print("Aucun modele importable.")
        return 1

    mode = "flush" if args.flush else ("append" if args.append else "skip-existing")

    print(f"Source        : {os.path.abspath(args.source)}")
    print(f"Export du     : {manifest.get('exported_at')} (base {manifest.get('database')})")
    print(f"Base cible    : {args.database}")
    print(f"Mode          : {mode}{'  [DRY-RUN]' if args.dry_run else ''}")
    print(f"Modeles       : {len(entries)} / {sum(e['count'] for e in entries)} lignes attendues\n")

    if mode == "flush" and not args.dry_run and not args.yes:
        reponse = input(f"Vider puis recharger {len(entries)} tables de la base "
                        f"'{args.database}' ? Tapez OUI pour continuer : ")
        if reponse.strip().upper() != "OUI":
            print("Annule.")
            return 1

    connection = connections[args.database]
    results, all_m2m = [], []

    with transaction.atomic(using=args.database):
        with connection.constraint_checks_disabled():
            if mode == "flush" and not args.dry_run:
                print("Purge des tables :")
                truncate(models, args.database)
                print()

            for entry, model in zip(entries, models):
                try:
                    res = import_model(entry, args.source, args.database, args.batch,
                                       mode, args.dry_run, args.ignore_conflicts)
                except IntegrityError as exc:
                    transaction.set_rollback(True, using=args.database)
                    report_integrity_error(entry, model, args, exc)
                    return 1
                results.append(res)
                all_m2m.extend(res["m2m"])
                if res["missing_file"]:
                    print(f"  {entry['model']:<45} FICHIER ABSENT ({entry['file']})")
                    continue
                detail = f"{res['created']:>10} inserees"
                if res["skipped"]:
                    detail += f", {res['skipped']} ignorees (deja presentes)"
                if res["rejected"]:
                    detail += f", {res['rejected']} refusees (conflit de contrainte)"
                print(f"  {entry['model']:<45} {detail}")
                if res["unknown_fields"]:
                    print(f"      champs inconnus ignores : {', '.join(res['unknown_fields'])}")

            liens, introuvables = import_m2m(all_m2m, args.database,
                                             args.batch, args.dry_run)
            if liens:
                print(f"\n  Liaisons ManyToMany recreees : {liens}")
            if introuvables:
                print("\n  Liaisons ManyToMany perdues (cible absente de cette base) :")
                for (label, key), nombre in introuvables.most_common():
                    print(f"    {label} '{key}' : {nombre} liaisons")

        if not args.dry_run:
            reset_sequences(models, args.database)

        if args.dry_run:
            transaction.set_rollback(True, using=args.database)

    total = sum(r["created"] for r in results)
    print(f"\nTotal : {total} lignes {'simulees' if args.dry_run else 'importees'}.")
    refusees = sum(r["rejected"] for r in results)
    if refusees:
        print(f"{refusees} lignes refusees pour conflit de contrainte (--ignore-conflicts).")
    if unknown:
        ignorees = sum(e["count"] for e in unknown)
        print(f"{len(unknown)} modeles inconnus ignores ({ignorees} lignes) : "
              f"{', '.join(e['model'] for e in unknown)}")
    if args.dry_run:
        print("Aucune ecriture effectuee (dry-run, transaction annulee).")
    connections.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
