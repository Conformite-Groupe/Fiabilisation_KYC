import csv
import os
import sys
import chardet
import logging
import django
from datetime import datetime
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from django.db import transaction, connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Kyc_pm, Kyc_pp

# --- 1. CONFIGURATION ---
STRICT_FIELD_LIMIT = 131072
csv.field_size_limit(STRICT_FIELD_LIMIT)

FILIALES = ['SN]']
CHEMIN_BASE = r"C:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\data"
DELIMITEUR_CSV = ";"
BULK_SIZE = 50000
MAX_DB_WORKERS = 4

# --- 2. LOGGING ---
def setup_logging():
    log_dir = os.path.join(os.getcwd(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger('KYC_Importer')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    if not logger.hasHandlers():
        logger.addHandler(ch)
        fh = RotatingFileHandler(
            os.path.join(log_dir, 'import_kyc.log'),
            maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

logger = setup_logging()

# --- 3. REJETS ---
def log_rejected_line(filename, line_num, error_msg):
    reject_file = os.path.join(CHEMIN_BASE, "lignes_ignorees.txt")
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(reject_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Fichier: {filename} | Ligne: {line_num} | Erreur: {error_msg}\n")

# --- 4. UTILITAIRES ---
def normalize_header(name):
    return (name or "").replace("\ufeff", "").strip().upper()

def pick_value(row_norm, candidates):
    for col in candidates:
        val = row_norm.get(col, "")
        if val:
            return val.strip()
    return (row_norm.get(candidates[0], "") or "").strip() if candidates else ""

def unique_values(values):
    seen = set()
    unique = []
    for value in values:
        normalized = normalize_header(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(value)
    return unique

FIELD_ALIASES = {
    "LIB_AGENCE": ["AGENCELIB", "AGENCE_LIB", "LIBELLE_AGENCE", "LIB AGENCE"],
    "ORIGINE_REV": ["ORIGINE_REVENU", "ORIGINE_REVENUS", "ORIGINE REVENU", "ORIGINE REVENUS"],
    "PAYS_RESID": ["PAYS_RESIDENCE", "PAYS_RESID", "PAYS RESIDENCE", "PAYS RESID"],
    "NUMID": ["NUM_ID", "NUMERO_ID", "NUMERO_IDENTITE", "NUMERO DOCUMENT", "NUMERO_DOCUMENT"],
    "DATVALID": ["DATE_VALIDITE", "DAT_VALID", "DATE VALIDITE", "DATE_EXPIRATION", "DATE EXPIRATION"],
    "DATNAIS": ["DATE_NAISSANCE", "DAT_NAIS", "DATE NAISSANCE", "DN"],
    "DATOUV": ["DATE_OUVERTURE", "DAT_OUV", "DATE OUVERTURE"],
    "PAYNAIS": ["PAYS_NAISSANCE", "PAYS NAISSANCE", "PAYS_NAIS"],
    "SALAIRE": ["REVENU", "REVENUS", "REVENU_MENSUEL", "SALAIRE_MENSUEL"],
    "TEL": ["TELEPHONE", "PHONE", "MOBILE"],
    "IDP": ["IDP", "IDENTIFIANT_PP", "IDENTIFIANT CLIENT", "ID_CLIENT"],
    "IDM": ["IDM", "IDENTIFIANT_PM", "IDENTIFIANT CLIENT", "ID_CLIENT"],
    "RCSNO": ["RCCM", "RCS", "NUMERO_RCS", "RCS NO"],
}

def build_model_mapping(model):
    mapping = {}
    for field in model._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        name = field.name
        mapping[name] = unique_values([
            name,
            name.upper(),
            *FIELD_ALIASES.get(name, []),
        ])
    return mapping

# --- 5. INSERTION EN THREAD (compatible MSSQL) ---
def _bulk_insert(model, batch):
    connection.close()  # Nouvelle connexion propre dans ce thread
    model.objects.bulk_create(batch)  # Sans ignore_conflicts (non supporté par MSSQL)

# --- 6. IMPORTATION ---
def importer_csv_optimise(path, model, mapping, code_filiale):
    inserted = 0
    filename = os.path.basename(path)
    logger.info(f"--- Lecture de {filename} ---")

    # Détection encodage sur 50 Ko
    enc = 'utf-8'
    try:
        with open(path, 'rb') as f:
            raw = f.read(51200)
            enc = chardet.detect(raw)['encoding'] or 'utf-8'
    except Exception:
        pass

    # Mapping candidats pré-normalisés (une seule fois avant la boucle)
    mapping_norm = {
        field: [normalize_header(c) for c in (
            [candidates] if isinstance(candidates, str) else candidates
        )]
        for field, candidates in mapping.items()
    }

    pending_futures = []

    try:
        with open(path, newline="", encoding=enc, errors='replace') as f:
            reader = csv.DictReader(f, delimiter=DELIMITEUR_CSV)

            if reader.fieldnames:
                reader.fieldnames = [normalize_header(fn) for fn in reader.fieldnames]

            all_rows = []

            with ThreadPoolExecutor(max_workers=MAX_DB_WORKERS) as executor:
                for line_counter, row in enumerate(reader, start=2):
                    try:
                        row_norm = {k: (v or "").strip() for k, v in row.items() if k}

                        data = {}
                        for field, candidates in mapping_norm.items():
                            data[field] = pick_value(row_norm, candidates)

                        for num_field in ("CAPITAL", "CA", "RESULTAT"):
                            if num_field in data:
                                data[num_field] = data[num_field].replace(",", ".").replace(" ", "")

                        data["FILIALE"] = f"BOA {code_filiale}"
                        all_rows.append(model(**data))

                        if len(all_rows) >= BULK_SIZE:
                            batch = all_rows
                            all_rows = []
                            future = executor.submit(_bulk_insert, model, batch)
                            pending_futures.append((future, len(batch)))
                            inserted += len(batch)
                            logger.info(f"    -> {inserted} lignes soumises...")

                    except Exception as e:
                        log_rejected_line(filename, line_counter, f"Erreur: {e}")

                # Dernier batch
                if all_rows:
                    future = executor.submit(_bulk_insert, model, all_rows)
                    pending_futures.append((future, len(all_rows)))
                    inserted += len(all_rows)

                # Attente des insertions + gestion erreurs
                for future, count in pending_futures:
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Erreur insertion batch ({count} lignes) : {e}")

    except Exception as e:
        logger.critical(f"🛑 Erreur fatale sur {filename} : {e}")

    logger.info(f"✅ {filename} : {inserted} lignes insérées.")
    return inserted


# --- 7. MAPPINGS ---
MAPPING_PM = build_model_mapping(Kyc_pm)
MAPPING_PP = build_model_mapping(Kyc_pp)


# --- 8. TRAITEMENT PAR FILIALE ---
def traiter_filiale(code):
    logger.info(f"\n>>> FILIALE {code}")

    with transaction.atomic():
        Kyc_pm.objects.filter(FILIALE=f"BOA {code}").delete()
        Kyc_pp.objects.filter(FILIALE=f"BOA {code}").delete()

    pm_f = os.path.join(CHEMIN_BASE, f"pm_{code}_STOCK_F.csv")
    pp_f = os.path.join(CHEMIN_BASE, f"pp_{code}_STOCK_F.csv")

    if os.path.exists(pm_f):
        importer_csv_optimise(pm_f, Kyc_pm, MAPPING_PM, code)
    if os.path.exists(pp_f):
        importer_csv_optimise(pp_f, Kyc_pp, MAPPING_PP, code)


# --- 9. MAIN ---
if __name__ == '__main__':
    with open(os.path.join(CHEMIN_BASE, "lignes_ignorees.txt"), "w", encoding="utf-8") as f:
        f.write(f"--- REJETS DU {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    if len(FILIALES) == 1:
        traiter_filiale(FILIALES[0])
    else:
        with ProcessPoolExecutor(max_workers=min(len(FILIALES), os.cpu_count())) as executor:
            futures = {executor.submit(traiter_filiale, code): code for code in FILIALES}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Erreur filiale {code} : {e}")

    logger.info("\n✨ Processus terminé.")
