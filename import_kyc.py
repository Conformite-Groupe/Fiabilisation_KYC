import csv
import os
import sys
import chardet
import logging
import django
from datetime import datetime
from logging.handlers import RotatingFileHandler
from django.db import transaction

# Configuration de l'environnement Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Kyc_pm, Kyc_pp

# --- 1. CONFIGURATION GLOBALE ---

# On fixe une limite stricte. Si une cellule dépasse 128 Ko, on rejette la ligne.
# Cela évite que Python ne consomme trop de RAM sur une ligne malformée.
STRICT_FIELD_LIMIT = 131072  # 128 Ko
csv.field_size_limit(STRICT_FIELD_LIMIT)

#FILIALES = ['BJ','NE','BF','MR','TG', 'CI','RDC']

FILIALES = ['MG']



CHEMIN_BASE = r"C:\Fiabilisation KYC\Python\data"
DELIMITEUR_CSV = ";"
BULK_SIZE = 50000

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
        fh = RotatingFileHandler(os.path.join(log_dir, 'import_kyc.log'), maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

logger = setup_logging()

# --- 3. GESTION DES REJETS ---

def log_rejected_line(filename, line_num, error_msg):
    reject_file = os.path.join(CHEMIN_BASE, "lignes_ignorees.txt")
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(reject_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Fichier: {filename} | Ligne CSV: {line_num} | Erreur: {error_msg}\n")

# --- 4. FONCTIONS UTILES ---

def normalize_header(name):
    return (name or "").strip().upper()


def pick_value(row_norm, candidates):
    for col in candidates:
        val = row_norm.get(col, "")
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    if candidates:
        return (row_norm.get(candidates[0], "") or "").strip()
    return ""

# --- 5. FONCTION D'IMPORTATION ---

def importer_csv_optimise(path, model, mapping, code_filiale):
    inserted = 0
    all_rows = [] 
    filename = os.path.basename(path)
    
    logger.info(f"--- Lecture de {filename} ---")

    # Détection encodage
    enc = 'utf-8'
    try:
        with open(path, 'rb') as f:
            enc = chardet.detect(f.read(10000))['encoding'] or 'utf-8'
    except: pass
    
    try:
        with open(path, newline="", encoding=enc, errors='replace') as f:
            reader = csv.DictReader(f, delimiter=DELIMITEUR_CSV)
            if reader.fieldnames:
                reader.fieldnames = [normalize_header(fn) for fn in reader.fieldnames]
            
            line_counter = 1 
            # On utilise une boucle while avec next() pour un contrôle total sur l'itérateur
            while True:
                line_counter += 1
                try:
                    row = next(reader)
                except StopIteration:
                    break
                except csv.Error as e:
                    # C'est ici que l'on intercepte "field larger than field_size_limit"
                    # L'itérateur passe automatiquement à la ligne suivante
                    logger.warning(f"❌ {filename} : Ligne {line_counter} rejetée immédiatement (Taille excessive).")
                    log_rejected_line(filename, line_counter, "Ligne trop longue / Malformée")
                    continue 

                try:
                    row_norm = {normalize_header(k): (v or "") for k, v in row.items()}

                    data = {}
                    for field, candidates in mapping.items():
                        if isinstance(candidates, str):
                            candidates = [candidates]
                        candidates = [normalize_header(c) for c in candidates]
                        data[field] = pick_value(row_norm, candidates)
                    
                    # Nettoyage numérique
                    for num_field in ["CAPITAL", "CA", "RESULTAT"]:
                        if num_field in data:
                            data[num_field] = data[num_field].replace(",", ".").replace(" ", "")

                    data["FILIALE"] = f"BOA {code_filiale}"
                    all_rows.append(model(**data))
                    
                    if len(all_rows) >= BULK_SIZE:
                        model.objects.bulk_create(all_rows)
                        inserted += len(all_rows)
                        all_rows = []
                        logger.info(f"    -> {inserted} lignes insérées...")

                except Exception as e:
                    log_rejected_line(filename, line_counter, f"Erreur data: {e}")

            if all_rows:
                model.objects.bulk_create(all_rows)
                inserted += len(all_rows)

    except Exception as e:
        logger.critical(f"🛑 Erreur fatale sur {filename} : {e}")

    return inserted

# --- 6. MAPPINGS ET MAIN ---
# (Mappings alignes sur les modeles Kyc_pm et Kyc_pp)

MAPPING_PM = {
    "AGENCE": ["AGENCE"],
    "LIB_AGENCE": ["LIB_AGENCE", "AGENCELIB","AGENCE_LIB"],
    "EXPL": ["EXPL"],
    "CLIENT": ["CLIENT"],
    "AGEC": ["AGEC"],
    "CODAPE": ["CODAPE"],
    "IDM": ["IDM"],
    "RCSNO": ["RCSNO"],
    "CAPITAL": ["CAPITAL"],
    "CA": ["CA"],
    "RESULTAT": ["RESULTAT"],
    "ORIGINE_REV": ["ORIGINE_REV", "ORIGINE_REVENU"],
    "DATOUV": ["DATOUV"],
    "TEL": ["TEL"],
    "DEVISE": ["DEVISE"],
    "RESID": ["RESID"],
}

MAPPING_PP = {
    "AGENCE": ["AGENCE"],
    "LIB_AGENCE": ["LIB_AGENCE", "AGENCELIB", "AGENCE_LIB"],
    "EXPL": ["EXPL"],
    "CLIENT": ["CLIENT"],
    "CODAPE": ["CODAPE"],
    "IDP": ["IDP"],
    "PAYNAIS": ["PAYNAIS"],
    "PROFESSION": ["PROFESSION"],
    "ADRESSE": ["ADRESSE"],
    "PAYS_RESID": ["PAYS_RESID"],
    "NUMID": ["NUMID"],
    "SALAIRE": ["SALAIRE"],
    "ORIGINE_REV": ["ORIGINE_REV", "ORIGINE_REVENU"],
    "DATVALID": ["DATVALID"],
    "TEL": ["TEL"],
    "DATOUV": ["DATOUV"],
    "PPE": ["PPE"],
    "DEVISE": ["DEVISE"],
    "RESID": ["RESID"],
}


if __name__ == '__main__':
    with open(os.path.join(CHEMIN_BASE, "lignes_ignorees.txt"), "w", encoding="utf-8") as f:
        f.write(f"--- REJETS DU {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    for code in FILIALES:
        logger.info(f"\n>>> FILIALE {code}")
        with transaction.atomic():
            Kyc_pm.objects.filter(FILIALE=f"BOA {code}").delete()
            Kyc_pp.objects.filter(FILIALE=f"BOA {code}").delete()

        pm_f = os.path.join(CHEMIN_BASE, f"pm_{code}_STOCK_F.csv")
        if os.path.exists(pm_f): importer_csv_optimise(pm_f, Kyc_pm, MAPPING_PM, code)
        
        pp_f = os.path.join(CHEMIN_BASE, f"pp_{code}_STOCK_F.csv")
        if os.path.exists(pp_f): importer_csv_optimise(pp_f, Kyc_pp, MAPPING_PP, code)

    logger.info("\n✨ Processus terminé.")
