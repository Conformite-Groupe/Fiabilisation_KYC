"""Import combine des donnees de la plateforme KYC.

Remplace a lui seul import_users.py, import_expl.py, import_data.py et
import_data_kyc.py. Recharge un repertoire produit par export_data_all.py,
dans l'ordre des dependances :

    users   profils ProfileV, reconnus par username : cree ceux qui manquent,
            met a jour les autres. Groupes et permissions rejoues par nom.
    expl    met a jour le seul code_expl des profils existants.
    data    REMPLACE TauxEvolution, TauxEvolution_filiale, Devise et Notation.
            Aucune notation n'est perdue : si l'agent ou le notateur est absent
            de cette base, son profil est recree a partir de l'identite portee
            par l'export (username, email ou code expl), desactive et sans mot
            de passe utilisable. Ces creations sont listees dans le rapport.
    kyc     Kyc_pp et Kyc_pm, en --kyc-mode flush (defaut) ou append.

Tout se joue dans une seule transaction : au moindre echec, rien n'est ecrit.

Exemples
--------
    python import_data_all.py data_all_20260805_1930
    python import_data_all.py data_all_20260805_1930 --sections users expl
    python import_data_all.py data_all_20260805_1930 --kyc-mode append
    python import_data_all.py data_all_20260805_1930 --dry-run
    python import_data_all.py data_all_20260805_1930 --skip-passwords --yes
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
from django.db import IntegrityError, connections, transaction

SECTIONS = ["users", "expl", "data", "kyc"]
DATA_MODELS = {
    "taux_evolution": "kyc.TauxEvolution",
    "taux_evolution_filiale": "kyc.TauxEvolution_filiale",
    "devise": "kyc.Devise",
}
PROGRESS_STEP = 100000
CHAMPS_SENSIBLES = ("password", "last_login")


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


def charger_json(base_dir, nom):
    chemin = os.path.join(base_dir, nom)
    if not os.path.exists(chemin):
        return None
    with open(chemin, encoding="utf-8") as fh:
        return json.load(fh)


def index_profils(using):
    model = django_apps.get_model("accounts.ProfileV")
    index = {}
    for profil in model._default_manager.using(using).all():
        for cle in (profil.username, profil.email, profil.code_expl):
            if cle:
                index.setdefault(str(cle).strip().lower(), profil)
    return index


def retrouver(index, ident):
    if not ident:
        return None
    for cle in (ident.get("username"), ident.get("email"), ident.get("expl")):
        if cle:
            profil = index.get(str(cle).strip().lower())
            if profil:
                return profil
    return None


def indexer(index, profil):
    for cle in (profil.username, profil.email, profil.code_expl):
        if cle:
            index.setdefault(str(cle).strip().lower(), profil)


def recreer_profil(index, ident, using, dry_run):
    model = django_apps.get_model("accounts.ProfileV")
    ident = ident or {}
    username = (ident.get("username") or ident.get("email")
                or (f"expl_{ident['expl']}" if ident.get("expl") else None)
                or "agent_inconnu")

    if dry_run:
        return None, str(username)

    profil, cree = model._default_manager.using(using).get_or_create(
        username=str(username),
        defaults={
            "email": ident.get("email") or "",
            "code_expl": ident.get("expl") or "",
            "is_active": False,
        },
    )
    if cree:
        profil.set_unusable_password()
        profil.save(using=using, update_fields=["password"])
    indexer(index, profil)
    return profil, str(username)


def import_users(lignes, using, dry_run, skip_passwords):
    model = django_apps.get_model("accounts.ProfileV")
    from django.contrib.auth.models import Group, Permission

    champs = {f.attname for f in model._meta.concrete_fields}
    crees = maj = 0
    permissions_absentes = set()

    for data in lignes:
        data = dict(data)
        groupes = data.pop("groups", [])
        permissions = data.pop("user_permissions", [])
        username = data.pop("username", None)
        if not username:
            continue
        if skip_passwords:
            for champ in CHAMPS_SENSIBLES:
                data.pop(champ, None)
        defaults = {k: v for k, v in data.items() if k in champs}

        if dry_run:
            existe = model._default_manager.using(using).filter(username=username).exists()
            crees += not existe
            maj += existe
            continue

        obj, created = model._default_manager.using(using).update_or_create(
            username=username, defaults=defaults)
        crees += created
        maj += not created

        objets_groupes = []
        for nom in groupes:
            groupe = Group.objects.using(using).filter(name=nom).first()
            if groupe is None:
                groupe = Group.objects.using(using).create(name=nom)
            objets_groupes.append(groupe)
        obj.groups.set(objets_groupes)

        objets_perms = []
        for cle in permissions:
            app_label, _, codename = str(cle).partition(".")
            perm = Permission.objects.using(using).filter(
                content_type__app_label=app_label, codename=codename).first()
            if perm is None:
                permissions_absentes.add(cle)
                continue
            objets_perms.append(perm)
        obj.user_permissions.set(objets_perms)

    return {"crees": crees, "maj": maj,
            "permissions_absentes": sorted(permissions_absentes)}


def import_expl(lignes, using, dry_run):
    model = django_apps.get_model("accounts.ProfileV")
    index = {}
    for profil in model._default_manager.using(using).all():
        for cle in (profil.username, profil.email):
            if cle:
                index.setdefault(str(cle).strip().lower(), profil)

    maj, deja_ok, introuvables = 0, 0, []
    for ligne in lignes:
        profil = None
        for cle in (ligne.get("username"), ligne.get("email")):
            if cle:
                profil = index.get(str(cle).strip().lower())
                if profil:
                    break
        if profil is None:
            introuvables.append(ligne.get("username"))
            continue

        code = ligne.get("code_expl") or ""
        if (profil.code_expl or "").strip() == code:
            deja_ok += 1
            continue
        maj += 1
        if not dry_run:
            profil.code_expl = code
            profil.save(update_fields=["code_expl"], using=using)

    return {"maj": maj, "deja_ok": deja_ok, "introuvables": introuvables}


def inserer_brut(using, model, lignes, batch_size, dry_run):
    if not lignes:
        return 0
    connection = connections[using]
    champs = {f.attname for f in model._meta.concrete_fields if not f.primary_key}
    colonnes = [c for c in lignes[0] if c in champs]
    if not colonnes:
        return 0

    table = connection.ops.quote_name(model._meta.db_table)
    noms = ", ".join(connection.ops.quote_name(c) for c in colonnes)
    place = ", ".join(["%s"] * len(colonnes))
    sql = f"INSERT INTO {table} ({noms}) VALUES ({place})"

    total = 0
    if dry_run:
        return len(lignes)
    with connection.cursor() as cursor:
        for debut in range(0, len(lignes), batch_size):
            lot = [tuple(l.get(c) for c in colonnes)
                   for l in lignes[debut:debut + batch_size]]
            cursor.executemany(sql, lot)
            total += len(lot)
    return total


def import_data(export, using, batch_size, dry_run):
    resultats = {}

    if not dry_run:
        for label in list(DATA_MODELS.values()) + ["kyc.Notation"]:
            django_apps.get_model(label)._default_manager.using(using).all().delete()

    for cle, label in DATA_MODELS.items():
        model = django_apps.get_model(label)
        resultats[cle] = inserer_brut(using, model, export.get(cle, []),
                                      batch_size, dry_run)

    index = index_profils(using)
    notations, ignorees = [], []
    recrees = set()

    for data in export.get("notation", []):
        data = dict(data)
        ident_agent = data.pop("agent_ident", None)
        ident_note_par = data.pop("note_par_ident", None)
        agent = retrouver(index, ident_agent)
        note_par = retrouver(index, ident_note_par)

        if agent is None:
            agent, nom = recreer_profil(index, ident_agent, using, dry_run)
            recrees.add(nom)
        if note_par is None:
            note_par = agent if ident_note_par is None else retrouver(index, ident_note_par)
            if note_par is None:
                note_par, nom = recreer_profil(index, ident_note_par, using, dry_run)
                recrees.add(nom)

        if agent is None or note_par is None:
            ignorees.append(data)
            continue
        data["agent_id"] = agent.pk
        data["note_par_id"] = note_par.pk
        notations.append(data)

    notation_model = django_apps.get_model("kyc.Notation")
    if dry_run:
        resultats["notation"] = len(export.get("notation", []))
    else:
        resultats["notation"] = inserer_brut(using, notation_model, notations,
                                             batch_size, dry_run)
    resultats["notation_ignorees"] = len(ignorees)
    resultats["profils_recrees"] = sorted(recrees)
    return resultats


def aligner_colonnes(entree, model):
    source = entree["columns"]
    cible = {f.attname: f for f in model._meta.concrete_fields}
    colonnes, positions, defauts = [], [], []
    for nom, field in cible.items():
        colonnes.append(nom)
        positions.append(source.index(nom) if nom in source else None)
        defauts.append(None if nom in source else (None if field.null else ""))
    manquantes = [n for n, p in zip(colonnes, positions) if p is None]
    surplus = [n for n in source if n not in cible]
    return colonnes, positions, defauts, manquantes, surplus


def identity_insert(cursor, connection, table, actif):
    """Autorise l'ecriture explicite de la cle primaire (SQL Server seulement)."""
    if connection.vendor != "microsoft":
        return
    cursor.execute(f"SET IDENTITY_INSERT {table} {'ON' if actif else 'OFF'}")


def import_kyc(entree, base_dir, using, batch_size, mode, dry_run):
    model = django_apps.get_model(entree["model"])
    chemin = os.path.join(base_dir, entree["file"])
    if not os.path.exists(chemin):
        return {"inserted": 0, "missing_file": True, "manquantes": [], "surplus": []}

    colonnes, positions, defauts, manquantes, surplus = aligner_colonnes(entree, model)
    connection = connections[using]
    table = connection.ops.quote_name(model._meta.db_table)
    pk = model._meta.pk.attname
    # La cle primaire n'est ecrite que si l'export la porte reellement ; sinon
    # on la retire pour laisser la base l'attribuer.
    if pk in colonnes and positions[colonnes.index(pk)] is None:
        i = colonnes.index(pk)
        for liste in (colonnes, positions, defauts):
            liste.pop(i)
        manquantes = [n for n in manquantes if n != pk]
    avec_pk = pk in colonnes

    if mode == "flush" and not dry_run:
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table}")

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
        if avec_pk and not dry_run:
            identity_insert(cursor, connection, table, True)
        try:
            for row in read_rows(chemin):
                lot.append(tuple(row[p] if p is not None else d
                                 for p, d in zip(positions, defauts)))
                if len(lot) >= batch_size:
                    flush(cursor)
            flush(cursor)
        finally:
            if avec_pk and not dry_run:
                identity_insert(cursor, connection, table, False)

    return {"inserted": inserted, "missing_file": False,
            "manquantes": manquantes, "surplus": surplus}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import combine des donnees KYC.")
    parser.add_argument("source", help="Repertoire produit par export_data_all.py.")
    parser.add_argument("--database", "-d", default="default",
                        help="Alias de base cible defini dans settings.DATABASES.")
    parser.add_argument("--sections", nargs="*", choices=SECTIONS, default=SECTIONS,
                        help=f"Sections a importer (defaut : {' '.join(SECTIONS)}).")
    parser.add_argument("--kyc-mode", choices=["flush", "append"], default="flush",
                        help="flush vide Kyc_pp / Kyc_pm avant rechargement (defaut).")
    parser.add_argument("--batch", type=int, default=5000,
                        help="Taille des lots d'insertion (defaut 5000).")
    parser.add_argument("--skip-passwords", action="store_true",
                        help="Ne pas importer les mots de passe ni last_login.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule : lit tout et compte, sans ecrire.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Ne pas demander de confirmation.")
    args = parser.parse_args(argv)

    manifest = charger_json(args.source, "manifest_data_all.json")
    if manifest is None:
        print(f"manifest_data_all.json introuvable dans {args.source}")
        return 1

    presentes = {e["section"] for e in manifest["entries"]}
    sections = [s for s in SECTIONS if s in args.sections and s in presentes]
    if not sections:
        print("Aucune section a importer.")
        print(f"Sections presentes dans l'export : {', '.join(sorted(presentes))}")
        return 1

    print(f"Source        : {os.path.abspath(args.source)}")
    print(f"Export du     : {manifest.get('exported_at')} (base {manifest.get('database')})")
    print(f"Base cible    : {args.database}")
    print(f"Sections      : {', '.join(sections)}")
    print(f"Mode KYC      : {args.kyc_mode}{'  [DRY-RUN]' if args.dry_run else ''}")
    if manifest.get("filiales"):
        print(f"Filiales      : {', '.join(manifest['filiales'])}")
    print(f"Lignes        : {manifest.get('total_rows')} attendues\n")

    if args.dry_run and "users" in sections:
        print("En dry-run les profils ne sont pas reellement crees : les sections")
        print("expl et notation sont donc comptees comme si la base restait vide.")
        print("Leurs chiffres sont pessimistes, ceux d'un import reel seront meilleurs.\n")

    destructif = []
    if "data" in sections:
        destructif.append("TauxEvolution, TauxEvolution_filiale, Devise, Notation")
    if "kyc" in sections and args.kyc_mode == "flush":
        destructif.append("Kyc_pp, Kyc_pm")

    if destructif and not args.dry_run and not args.yes:
        print("Ces tables vont etre VIDEES avant rechargement :")
        for ligne in destructif:
            print(f"  - {ligne}")
        reponse = input(f"\nConfirmer sur la base '{args.database}' ? Tapez OUI : ")
        if reponse.strip().upper() != "OUI":
            print("Annule.")
            return 1
        print()

    entrees = {e["section"]: e for e in manifest["entries"] if e["section"] != "kyc"}
    entrees_kyc = [e for e in manifest["entries"] if e["section"] == "kyc"]

    try:
        with transaction.atomic(using=args.database):
            if "users" in sections:
                lignes = charger_json(args.source, entrees["users"]["file"]) or []
                res = import_users(lignes, args.database, args.dry_run, args.skip_passwords)
                print(f"  users                    {res['crees']} crees, {res['maj']} mis a jour")
                if res["permissions_absentes"]:
                    print(f"    permissions inconnues ici, ignorees : "
                          f"{', '.join(res['permissions_absentes'])}")

            if "expl" in sections:
                lignes = charger_json(args.source, entrees["expl"]["file"]) or []
                res = import_expl(lignes, args.database, args.dry_run)
                print(f"  codes expl               {res['maj']} mis a jour, "
                      f"{res['deja_ok']} deja alignes")
                if res["introuvables"]:
                    apercu = ", ".join(str(u) for u in res["introuvables"][:10])
                    print(f"    {len(res['introuvables'])} profils absents ici : {apercu}")

            if "data" in sections:
                export = charger_json(args.source, entrees["data"]["file"]) or {}
                res = import_data(export, args.database, args.batch, args.dry_run)
                for cle in ("taux_evolution", "taux_evolution_filiale", "devise", "notation"):
                    print(f"  {cle:<24} {res.get(cle, 0):>10} lignes")
                if res.get("profils_recrees"):
                    noms = ", ".join(res["profils_recrees"][:10])
                    print(f"    {len(res['profils_recrees'])} profils recrees pour "
                          f"conserver les notations : {noms}")
                    print("      comptes desactives, mot de passe inutilisable, "
                          "a rattacher manuellement si besoin")
                if res.get("notation_ignorees"):
                    print(f"    {res['notation_ignorees']} notations ignorees "
                          f"(identite de l'agent totalement absente de l'export)")

            if "kyc" in sections:
                for entree in entrees_kyc:
                    print(f"  {entree['model']}")
                    res = import_kyc(entree, args.source, args.database,
                                     args.batch, args.kyc_mode, args.dry_run)
                    if res["missing_file"]:
                        print(f"    FICHIER ABSENT ({entree['file']})")
                        continue
                    print(f"    {res['inserted']} lignes inserees")
                    if res["manquantes"]:
                        print(f"    colonnes absentes de l'export, remplies a vide : "
                              f"{', '.join(res['manquantes'])}")
                    if res["surplus"]:
                        print(f"    colonnes de l'export inconnues ici, ignorees : "
                              f"{', '.join(res['surplus'])}")

            if args.dry_run:
                transaction.set_rollback(True, using=args.database)

    except IntegrityError as exc:
        print(f"\nECHEC : {exc}")
        print("Aucune ecriture conservee : la transaction a ete annulee.")
        return 1

    if args.dry_run:
        print("\nAucune ecriture effectuee (dry-run, transaction annulee).")
    else:
        print("\nImport termine.")
    connections.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
