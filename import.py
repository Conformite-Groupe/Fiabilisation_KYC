import csv
import os
import django
import chardet
from django.db import transaction, IntegrityError, DataError
import sys

                                                     
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Agents                                                  

                          
chemin_base = r"C:\Fiabilisation KYC\Python\data"

                                                    
CHAMPS_A_METTRE_A_JOUR = ['agence', 'agence_lib', 'nom', 'email'] 

def import_agents_from_folder(folder_path):
    """
    Importe les agents en gérant la conversion 'NUMERIQUE' pour les agences digitales
    et évite les doublons de préfixe BOA.
    """
                                 
    csv_files = [
        f for f in os.listdir(folder_path)
        if f.lower().startswith("agents_") and f.lower().endswith(".csv")
    ]

    if not csv_files:
        print("⚠️ Aucun fichier agents_XX.csv trouvé.")
        return

    total_created = 0
    total_updated = 0
    
                                                                                  
    agents_existants = {
        (agent.expl, agent.filiale): agent
        for agent in Agents.objects.all()
    }

    for csv_file in csv_files:
        file_path = os.path.join(folder_path, csv_file)
        print(f"\n➡️ Import du fichier : {csv_file}")

        agents_to_create = []
        agents_to_update = []
        
        try:
                                                                                    
            with open(file_path, 'rb') as f_bin:
                raw_data = f_bin.read(10000)
                result = chardet.detect(raw_data)
                encoding = result['encoding'] or 'utf-8'

            with open(file_path, mode='r', encoding=encoding, errors='replace') as file:
                reader = csv.DictReader(file, delimiter=';') 

                for row in reader:
                                                                                     
                    data = {k.lower(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
                    
                    filiale_csv_code = data.get("filiale")
                    expl = data.get("expl")
                    
                    if not expl or not filiale_csv_code:
                        continue

                                                                      
                    if not filiale_csv_code.upper().startswith("BOA "):
                        filiale_db_value = f"BOA {filiale_csv_code}"
                    else:
                        filiale_db_value = filiale_csv_code
                    
                                                        
                                                                          
                    ag_brute = data.get("agence") or ""
                    ag_lib_brute = data.get("agencelib") or ""
                    
                    mots_cles_digitaux = ["DIGITAL", "NUMERIQUE", "ONLINE", "E-BANK", "DISTANT"]
                    
                                                                                 
                    if any(mot in ag_brute.upper() for mot in mots_cles_digitaux) or\
                       any(mot in ag_lib_brute.upper() for mot in mots_cles_digitaux):
                        agence_finale = "NUMERIQUE"
                    else:
                        agence_finale = ag_brute

                                                                  
                    key = (expl, filiale_db_value)
                    existing_agent = agents_existants.get(key)

                                                       
                    cleaned_data = {
                        "filiale": filiale_db_value,
                        "expl": expl,
                        "agence": agence_finale,
                        "agence_lib": ag_lib_brute,
                        "nom": data.get("nom"),
                        "email": data.get("email"),
                    }

                                            
                    if existing_agent:
                        changed = False
                        for field in CHAMPS_A_METTRE_A_JOUR:
                                                                                 
                            val_csv = cleaned_data.get(field)
                            if field == 'agence_lib':                                    
                                val_csv = ag_lib_brute

                            if getattr(existing_agent, field) != val_csv:
                                setattr(existing_agent, field, val_csv)
                                changed = True
                        
                        if changed:
                            agents_to_update.append(existing_agent)

                                         
                    else:
                        agent = Agents(
                            filiale=cleaned_data["filiale"],
                            expl=cleaned_data["expl"],
                            agence=cleaned_data["agence"],
                            agence_lib=cleaned_data["agence_lib"],
                            nom=cleaned_data["nom"],
                            email=cleaned_data["email"],
                        )
                        agents_to_create.append(agent)
                
                                             
                with transaction.atomic():
                    if agents_to_create:
                        Agents.objects.bulk_create(agents_to_create)
                        total_created += len(agents_to_create)
                        print(f"   ✓ {len(agents_to_create)} nouveaux agents créés.")
                    
                    if agents_to_update:
                                                                                       
                        Agents.objects.bulk_update(agents_to_update, CHAMPS_A_METTRE_A_JOUR)
                        total_updated += len(agents_to_update)
                        print(f"   ✓ {len(agents_to_update)} agents mis à jour.")

        except Exception as e:
            print(f"❌ Erreur fichier {csv_file}: {e}")
            continue

    print(f"\n🎉 Import terminé !")
    print(f"   Total créés : {total_created} | Total mis à jour : {total_updated}")

if __name__ == "__main__":
    import_agents_from_folder(chemin_base)


import csv
import os
import sys
import chardet
import logging
import django
from datetime import datetime
from logging.handlers import RotatingFileHandler
from django.db import transaction

                                         
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Kyc_pm, Kyc_pp

                                  

                                                                                 
                                                                        
STRICT_FIELD_LIMIT = 131072          
csv.field_size_limit(STRICT_FIELD_LIMIT)

FILIALES = ["SN",'NE','BF','MR','TG', 'CI','RDC']


CHEMIN_BASE = r"C:\Fiabilisation KYC\Python\data"
DELIMITEUR_CSV = ";" 
BULK_SIZE = 5000 

                    

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

                               

def log_rejected_line(filename, line_num, error_msg):
    reject_file = os.path.join(CHEMIN_BASE, "lignes_ignorees.txt")
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(reject_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Fichier: {filename} | Ligne CSV: {line_num} | Erreur: {error_msg}\n")

                             

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


MODEL_FIELDS_CACHE = {}
def get_model_field_names(model):
    cached = MODEL_FIELDS_CACHE.get(model)
    if cached is not None:
        return cached
    fields = {f.name for f in model._meta.fields}
    MODEL_FIELDS_CACHE[model] = fields
    return fields

                                   

def importer_csv_optimise(path, model, mapping, code_filiale):
    inserted = 0
    all_rows = [] 
    filename = os.path.basename(path)
    
    logger.info(f"--- Lecture de {filename} ---")

                        
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
                                                                                            
            while True:
                line_counter += 1
                try:
                    row = next(reader)
                except StopIteration:
                    break
                except csv.Error as e:
                                                                                        
                                                                           
                    logger.warning(f"❌ {filename} : Ligne {line_counter} rejetée immédiatement (Taille excessive).")
                    log_rejected_line(filename, line_counter, "Ligne trop longue / Malformée")
                    continue 

                try:
                    row_norm = {normalize_header(k): (v or "") for k, v in row.items()}

                    data = {}
                    model_fields = get_model_field_names(model)
                    for field, candidates in mapping.items():
                        if isinstance(candidates, str):
                            candidates = [candidates]
                        candidates = [normalize_header(c) for c in candidates]
                        if field in model_fields:
                            data[field] = pick_value(row_norm, candidates)
                    
                                         
                    for num_field in ["CAPITAL", "CA", "RESULTAT"]:
                        if num_field in data:
                            data[num_field] = data[num_field].replace(",", ".").replace(" ", "")

                    if "FILIALE" in model_fields:
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

                             
                                   

MAPPING_PM = {
    "AGENCE": ["AGENCE"],
    "LIB_AGENCE": ["LIB_AGENCE", "AGENCELIB"],
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
    "LIB_AGENCE": ["LIB_AGENCE", "AGENCELIB"],
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

    
