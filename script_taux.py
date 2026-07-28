import csv
import os
import re
import sys
import logging
from datetime import datetime
import argparse

import django

                                                       
                  
                                                       
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import TauxEvolution, TauxEvolution_filiale

                                                       
               
                                                       
DEFAULT_DATA_DIR = os.environ.get(
    "KYC_DATA_DIR",
    r"C:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\data",
)
DEFAULT_AGENT_FILE = "suivi_fiabilisation_agent.csv"
DEFAULT_GROUPE_FILE = "suivi_fiabilisation_groupe.csv"
BULK_SIZE = 5000

                                                       
            
                                                       
def setup_logging():
    logger = logging.getLogger("KYC_TAUX_IMPORT")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        console = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger

logger = setup_logging()

                                                       
          
                                                       
def normalize_header(name):
    s = (name or "").strip().upper().replace("\ufeff", "")
    s = re.sub(r"[\\s/\\-]+", "_", s)
    return s

def pick_value(row_norm, candidates):
    for col in candidates:
        val = row_norm.get(col, "")
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    if candidates:
        return (row_norm.get(candidates[0], "") or "").strip()
    return ""

def parse_date_multi(val):
    if not val:
        return None
    s = str(val).strip()
    if len(s) >= 10:
        s10 = s[:10]
        try:
            if "-" in s10:
                return datetime.strptime(s10, "%Y-%m-%d").date()
            if "/" in s10:
                return datetime.strptime(s10, "%d/%m/%Y").date()
        except ValueError:
            pass
    return None

def parse_taux(val):
    if val is None:
        return 0.0
    try:
        return float(str(val).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return 0.0

def normalize_filiale(val):
    if not val:
        return ""
    v = str(val).strip().upper()
    if v.startswith("BOA "):
        return v
    if len(v) <= 3:
        return f"BOA {v}"
    return v

def normalize_flux_stock(val):
    if not val:
        return ""
    v = str(val).strip().upper()
    if v in ("F", "FLUX"):
        return "F"
    if v in ("S", "STOCK"):
        return "S"
    return v

def normalize_pp_pm(val):
    if not val:
        return ""
    v = str(val).strip().upper()
    if v in ("P", "PP"):
        return "P"
    if v in ("M", "PM"):
        return "M"
    return v

def detect_encoding(path):
    try:
        import chardet                
        with open(path, "rb") as f:
            raw = f.read(50000)
        return chardet.detect(raw)["encoding"] or "utf-8"
    except Exception:
        return "utf-8"

def detect_delimiter(sample):
    if sample.count(";") >= sample.count(","):
        return ";"
    return ","

                                                       
                                  
                                                       
def import_taux_agents(path, default_filiale=None, clear=False):
    logger.info("=== IMPORT TAUX AGENTS ===")
    if not os.path.exists(path):
        logger.error(f"Fichier introuvable: {path}")
        return

    encoding = detect_encoding(path)
    inserted = 0
    skipped = 0
    cleared = set()
    objects_to_create = []
    unique_keys = set()

    warned_missing_filiale = False
    with open(path, "r", encoding=encoding, errors="replace") as f:
        sample = f.readline()
        delimiter = detect_delimiter(sample)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            logger.error("En-têtes vides pour le fichier agents.")
            return
        reader.fieldnames = [normalize_header(h) for h in reader.fieldnames]

        agent_cols = ["EXPL", "AGENT", "AGENTS", "CODE_EXPL", "CODE_AGENT", "EXPLOITANT"]
        date_cols = ["DATE", "DATE_NOTATION", "DATE_NOTE", "DATE_SUIVI", "DATEREV", "DATE_REV"]
        taux_cols = ["TAUX", "TAUX_AGENT", "SCORE", "NOTE", "POURCENTAGE"]
        filiale_cols = ["FILIALE", "FILIALE_CODE", "PAYS", "BOA"]
        agence_cols = ["AGENCE", "AG", "CODE_AGENCE"]
        flux_stock_cols = ["FLUX_STOCK", "FLUXSTOCK", "FLUX_STOCKS", "FLUX/STOCK", "FS"]
        pp_pm_cols = ["PP_PM", "PPPM", "PP/PM", "TYPE_PP_PM", "TYPE"]

        for row in reader:
            row_norm = {normalize_header(k): (v or "") for k, v in row.items()}

            agent = pick_value(row_norm, agent_cols)
            date_val = parse_date_multi(pick_value(row_norm, date_cols))
            taux_val = parse_taux(pick_value(row_norm, taux_cols))
            filiale = normalize_filiale(pick_value(row_norm, filiale_cols) or default_filiale)
            agence = pick_value(row_norm, agence_cols)
            flux_stock = normalize_flux_stock(pick_value(row_norm, flux_stock_cols))
            pp_pm = normalize_pp_pm(pick_value(row_norm, pp_pm_cols))

            if not filiale and not warned_missing_filiale:
                logger.warning(
                    "Filiale absente dans le CSV agents. Utilise --filiale-agent ou --filiale."
                )
                warned_missing_filiale = True

            if not agent or not date_val or not filiale:
                skipped += 1
                continue

            if clear and filiale not in cleared:
                TauxEvolution.objects.filter(filiale=filiale).delete()
                cleared.add(filiale)

            key = (filiale, agent, date_val, flux_stock, pp_pm)
            if key in unique_keys:
                continue
            unique_keys.add(key)

            objects_to_create.append(
                TauxEvolution(
                    filiale=filiale,
                    agence=agence,
                    expl=agent,
                    date=date_val,
                    taux=taux_val,
                    flux_stock=flux_stock,
                    pp_pm=pp_pm,
                )
            )

            if len(objects_to_create) >= BULK_SIZE:
                TauxEvolution.objects.bulk_create(objects_to_create)
                inserted += len(objects_to_create)
                objects_to_create.clear()

    if objects_to_create:
        TauxEvolution.objects.bulk_create(objects_to_create)
        inserted += len(objects_to_create)

    logger.info(f"Agents: {inserted} lignes importées, {skipped} ignorées")

                                                       
                                          
                                                       
def import_taux_groupe(path, default_filiale=None, clear=False):
    logger.info("=== IMPORT TAUX GROUPE ===")
    if not os.path.exists(path):
        logger.error(f"Fichier introuvable: {path}")
        return

    encoding = detect_encoding(path)
    inserted = 0
    skipped = 0
    cleared = set()
    objects_to_create = []
    unique_keys = set()

    warned_missing_filiale = False
    with open(path, "r", encoding=encoding, errors="replace") as f:
        sample = f.readline()
        delimiter = detect_delimiter(sample)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            logger.error("En-têtes vides pour le fichier groupe.")
            return
        reader.fieldnames = [normalize_header(h) for h in reader.fieldnames]

        filiale_cols = ["FILIALE", "FILIALE_CODE", "PAYS", "BOA"]
        date_cols = ["DATE", "DATE_SUIVI", "DATEREV", "DATE_REV"]
        flux_pm_cols = ["FLUX_PM", "FLUXPM", "FLUX_PM_PCT", "FLUX_PM_%", "FLUX_PM_PERCENT"]
        flux_pp_cols = ["FLUX_PP", "FLUXPP", "FLUX_PP_PCT", "FLUX_PP_%", "FLUX_PP_PERCENT"]
        stock_pm_cols = ["STOCK_PM", "STOCKPM", "STOCK_PM_PCT", "STOCK_PM_%", "STOCK_PM_PERCENT"]
        stock_pp_cols = ["STOCK_PP", "STOCKPP", "STOCK_PP_PCT", "STOCK_PP_%", "STOCK_PP_PERCENT"]

        for row in reader:
            row_norm = {normalize_header(k): (v or "") for k, v in row.items()}

            filiale = normalize_filiale(pick_value(row_norm, filiale_cols) or default_filiale)
            if not filiale:
                                                             
                filiale = "BOA Group"
                if not warned_missing_filiale:
                    logger.warning("Filiale absente dans le CSV groupe. Fallback sur 'BOA Group'.")
                    warned_missing_filiale = True
            date_val = parse_date_multi(pick_value(row_norm, date_cols))
            flux_pm = parse_taux(pick_value(row_norm, flux_pm_cols))
            flux_pp = parse_taux(pick_value(row_norm, flux_pp_cols))
            stock_pm = parse_taux(pick_value(row_norm, stock_pm_cols))
            stock_pp = parse_taux(pick_value(row_norm, stock_pp_cols))

            if not filiale or not date_val:
                skipped += 1
                continue

            if clear and filiale not in cleared:
                TauxEvolution_filiale.objects.filter(filiale=filiale).delete()
                cleared.add(filiale)

            key = (filiale, date_val)
            if key in unique_keys:
                continue
            unique_keys.add(key)

            objects_to_create.append(
                TauxEvolution_filiale(
                    filiale=filiale,
                    flux_PM=flux_pm,
                    flux_PP=flux_pp,
                    stock_PM=stock_pm,
                    stock_PP=stock_pp,
                    date=date_val,
                )
            )

            if len(objects_to_create) >= BULK_SIZE:
                TauxEvolution_filiale.objects.bulk_create(objects_to_create)
                inserted += len(objects_to_create)
                objects_to_create.clear()

    if objects_to_create:
        TauxEvolution_filiale.objects.bulk_create(objects_to_create)
        inserted += len(objects_to_create)

    logger.info(f"Groupe: {inserted} lignes importées, {skipped} ignorées")

                                                       
         
                                                       
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Taux Agents & Groupe")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Dossier contenant les fichiers CSV")
    parser.add_argument("--agent-file", default=DEFAULT_AGENT_FILE, help="Nom du fichier agents")
    parser.add_argument("--groupe-file", default=DEFAULT_GROUPE_FILE, help="Nom du fichier groupe")
    parser.add_argument("--filiale", help="Filiale par défaut si absente du CSV (ex: SN ou BOA SN)")
    parser.add_argument("--filiale-agent", help="Filiale par défaut pour le fichier agent")
    parser.add_argument("--filiale-groupe", help="Filiale par défaut pour le fichier groupe (sinon BOA Group)")
    parser.add_argument("--clear", action="store_true", help="Supprimer les lignes existantes pour la filiale avant import")
    parser.add_argument("--clear-agent", action="store_true", help="Supprimer les lignes agents avant import")
    parser.add_argument("--clear-groupe", action="store_true", help="Supprimer les lignes groupe avant import")

    args = parser.parse_args()

    agent_path = os.path.join(args.data_dir, args.agent_file)
    groupe_path = os.path.join(args.data_dir, args.groupe_file)

    clear_agent = args.clear or args.clear_agent
    clear_groupe = args.clear or args.clear_groupe

    logger.info(f"DATA DIR  : {args.data_dir}")
    logger.info(f"AGENT CSV : {agent_path}")
    logger.info(f"GROUPE CSV: {groupe_path}")

    filiale_agent = args.filiale_agent or args.filiale
    filiale_groupe = args.filiale_groupe or args.filiale

    import_taux_agents(agent_path, default_filiale=filiale_agent, clear=clear_agent)
    import_taux_groupe(groupe_path, default_filiale=filiale_groupe, clear=clear_groupe)
