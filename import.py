import csv
import os
import django
import chardet
from django.db import transaction, IntegrityError, DataError
import sys

# --- 1. Initialisation de l’environnement Django ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Agents  # Assure-toi que le modèle s'appelle bien Agents

# --- 2. Configuration ---
chemin_base = r"C:\Fiabilisation KYC\Python\data"

# Champs autorisés pour la mise à jour (bulk_update)
CHAMPS_A_METTRE_A_JOUR = ['agence', 'agence_lib', 'nom', 'email'] 

def import_agents_from_folder(folder_path):
    """
    Importe les agents en gérant la conversion 'NUMERIQUE' pour les agences digitales
    et évite les doublons de préfixe BOA.
    """
    # Identification des fichiers
    csv_files = [
        f for f in os.listdir(folder_path)
        if f.lower().startswith("agents_") and f.lower().endswith(".csv")
    ]

    if not csv_files:
        print("⚠️ Aucun fichier agents_XX.csv trouvé.")
        return

    total_created = 0
    total_updated = 0
    
    # Chargement en mémoire pour éviter des milliers de requêtes SQL (Performance)
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
            # Détection de l'encodage pour éviter les erreurs de caractères spéciaux
            with open(file_path, 'rb') as f_bin:
                raw_data = f_bin.read(10000)
                result = chardet.detect(raw_data)
                encoding = result['encoding'] or 'utf-8'

            with open(file_path, mode='r', encoding=encoding, errors='replace') as file:
                reader = csv.DictReader(file, delimiter=';') 

                for row in reader:
                    # Nettoyage : clés en minuscules et valeurs sans espaces inutiles
                    data = {k.lower(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
                    
                    filiale_csv_code = data.get("filiale")
                    expl = data.get("expl")
                    
                    if not expl or not filiale_csv_code:
                        continue

                    # --- GESTION DU FORMAT DE LA FILIALE (BOA XX) ---
                    if not filiale_csv_code.upper().startswith("BOA "):
                        filiale_db_value = f"BOA {filiale_csv_code}"
                    else:
                        filiale_db_value = filiale_csv_code
                    
                    # --- LOGIQUE NUMÉRIQUE (AGENCE) ---
                    # On récupère le code agence ou le libellé pour tester
                    ag_brute = data.get("agence") or ""
                    ag_lib_brute = data.get("agencelib") or ""
                    
                    mots_cles_digitaux = ["DIGITAL", "NUMERIQUE", "ONLINE", "E-BANK", "DISTANT"]
                    
                    # Si "DIGITAL" est présent dans le code ou le nom de l'agence
                    if any(mot in ag_brute.upper() for mot in mots_cles_digitaux) or \
                       any(mot in ag_lib_brute.upper() for mot in mots_cles_digitaux):
                        agence_finale = "NUMERIQUE"
                    else:
                        agence_finale = ag_brute

                    # Clé d'identification unique (expl + filiale)
                    key = (expl, filiale_db_value)
                    existing_agent = agents_existants.get(key)

                    # Préparation des données nettoyées
                    cleaned_data = {
                        "filiale": filiale_db_value,
                        "expl": expl,
                        "agence": agence_finale,
                        "agence_lib": ag_lib_brute,
                        "nom": data.get("nom"),
                        "email": data.get("email"),
                    }

                    # --- A. Mise à jour ---
                    if existing_agent:
                        changed = False
                        for field in CHAMPS_A_METTRE_A_JOUR:
                            # agence_lib est mappé depuis 'agencelib' dans le CSV
                            val_csv = cleaned_data.get(field)
                            if field == 'agence_lib': # cas particulier du mapping de nom
                                val_csv = ag_lib_brute

                            if getattr(existing_agent, field) != val_csv:
                                setattr(existing_agent, field, val_csv)
                                changed = True
                        
                        if changed:
                            agents_to_update.append(existing_agent)

                    # --- B. Création ---
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
                
                # --- SAUVEGARDE EN MASSE ---
                with transaction.atomic():
                    if agents_to_create:
                        Agents.objects.bulk_create(agents_to_create)
                        total_created += len(agents_to_create)
                        print(f"   ✓ {len(agents_to_create)} nouveaux agents créés.")
                    
                    if agents_to_update:
                        # On spécifie les champs à mettre à jour pour plus de précision
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
from datetime import datetime
import django
from django.db import transaction, IntegrityError, DataError
import chardet

# --- 1. Configuration Globale et Initialisation ---

# Augmenter la limite de taille de champ CSV si nécessaire
new_field_limit = 500000 
while True:
    try:
        csv.field_size_limit(new_field_limit)
        break
    except OverflowError:
        new_field_limit = int(new_field_limit / 2)

# Configuration de l'environnement Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

# Importation du modèle après la configuration de Django
from kyc.models import Anomalie 

# Paramètres d'exécution
filiales = ["SN",'BJ','NE','BF','MR','TG', 'CI','RDC','MG']


chemin_base = r"C:\Fiabilisation KYC\Python\data"
delimiteur_csv = ";" 

# Taille du lot pour l'insertion en masse (point clé d'optimisation)
BULK_SIZE = 5000 

# --- 2. Fonction de Secours (Débogage) ---

def bulk_create_fallback(rows, model):
    """ 
    Tente d'insérer les lignes d'un lot qui a échoué une par une pour isoler l'erreur.
    """
    inserted = 0
    for obj in rows:
        try:
            obj.save() 
            inserted += 1
        except Exception as e:
            pk_val = getattr(obj, 'CLIENT', getattr(obj, 'AGENCE', 'N/A'))
            print(f"  ❌ Échec insertion ligne isolée (Clé: {pk_val}) : {e}")
    return inserted

# --- 3. Fonction d'Importation OPTIMISÉE (bulk_create) ---

def importer_anom_optimise(path, model, mapping, code_filiale, delim=delimiteur_csv):
    """
    Lit le fichier CSV, prépare les objets en lots (Anomalie), 
    et utilise bulk_create pour une insertion en masse rapide.
    """
    inserted = 0
    all_rows = [] 
    
    print("\n-------------------------------------------------")
    print(f"Ouverture du fichier : {path} (Insertion par lots de {BULK_SIZE})")
    
    # --- Détection de l'encodage ---
    enc = 'utf-8' # Commencer par une valeur par défaut
    try:
        with open(path, 'rb') as fbin:
            sample = fbin.read(100000)
            detected = chardet.detect(sample)
        enc = detected.get('encoding') or 'utf-8'
        print(f"Encodage détecté : {enc}")
    except Exception as e:
        print(f"⚠️ Erreur de détection d'encodage : {e}. Utilisation de '{enc}'.")
    # -------------------------------

    try:
        # Note: L'encodage 'utf-8-sig' est souvent nécessaire pour les fichiers CSV créés par Excel
        # qui contiennent un Byte Order Mark (BOM).
        with open(path, newline="", encoding=enc, errors='replace') as f:
            reader = csv.DictReader(f, delimiter=delim, skipinitialspace=True)
            # Nettoyage des noms de colonnes (essentiel)
            if reader.fieldnames:
                reader.fieldnames = [h.strip() for h in reader.fieldnames]
                print("Colonnes lues :", reader.fieldnames)
            else:
                print("❌ Fichier CSV vide ou mal formaté (pas de noms de colonnes).")
                return 0

            
            for row in reader:
                data = {}
                line_num = reader.line_num # Pour le débogage
                
                try:
                    # 1. Traitement spécifique de la colonne AGENCE
                    ag = row.get("AGENCE", "").strip()
                    if not ag:
                        # Si "AGENCE" n'existe pas, essayer "Agence" (casse sensible)
                        ag = row.get("Agence", "").strip() 
                    
                    if not ag:
                        # Log si la clé AGENCE est introuvable ou vide
                        print(f"!! Ligne {line_num} ignorée : 'AGENCE' ou 'Agence' manquant/vide.")
                        continue

                    # 2. Préparation des données pour l'objet Anomalie
                    data = {
                        "FILIALE": f"BOA {code_filiale}",
                        "AGENCE": ag,
                        "EXPL": row.get(mapping["EXPL"], "").strip(),
                        "CLIENT": row.get(mapping["CLIENT"], "").strip(),
                        # Nettoyage des valeurs numériques (remplace virgule par point)
                        "ANOMALIE_AGE": row.get(mapping["ANOMALIE_AGE"], "").replace(",", "."),
                        "ANOMALIE_DATE_EER": row.get(mapping["ANOMALIE_DATE_EER"], "").replace(",", "."),
                        "ANOMALIE_CIN": row.get(mapping["ANOMALIE_CIN"], "").replace(",", "."),
                        "PPE": row.get(mapping["PPE"], "").replace(",", "."),
                    }
                    
                    # 3. Création de l'instance d'objet EN MÉMOIRE
                    obj = model(**data) 
                    all_rows.append(obj)
                    
                except (ValueError, TypeError, DataError, IntegrityError, Exception) as e:
                    # Erreurs de données sur une ligne (ex: donnée trop longue, conversion échouée)
                    print(f"❌ Erreur de préparation ligne {line_num}, row={row} : {e}")
                    
                
                # 4. Insertion par lots (Chunking)
                if len(all_rows) >= BULK_SIZE:
                    try:
                        model.objects.bulk_create(all_rows)
                        inserted += len(all_rows)
                        all_rows = [] 
                        print(f"   -> {inserted} lignes insérées...")
                    except Exception as e:
                        print(f"❌ Erreur d'insertion en masse du lot (après ligne {line_num}) : {e}.")
                        print("   -> Lancement du mode débogage lent (fallback) sur ce lot.")
                        inserted += bulk_create_fallback(all_rows, model)
                        all_rows = []

        # 5. Insertion du dernier lot restant
        if all_rows:
            try:
                model.objects.bulk_create(all_rows)
                inserted += len(all_rows)
            except Exception as e:
                print(f"❌ Erreur d'insertion en masse du dernier lot : {e}")
                print("   -> Lancement du mode débogage lent (fallback) sur le dernier lot.")
                inserted += bulk_create_fallback(all_rows, model)


    except Exception as e:
        print(f"❌ Erreur fatale lors de la lecture ou du traitement du fichier CSV : {e}")


    print(f"✅ {inserted} enregistrements créés dans {model.__name__} pour BOA {code_filiale}")
    print("-------------------------------------------------")
    return inserted

# --- 4. Définir les mappings (Identique à votre version) ---

mapping_anom = {
    "FILIALE": "FILIALE",
    "AGENCE": "AGENCE", # Sera géré par le code d'importation
    "EXPL": "EXPL",
    "CLIENT": "CLIENT",
    "ANOMALIE_AGE": "ANOMALIE_AGE",
    "ANOMALIE_DATE_EER": "ANOMALIE_DATE_EER",
    "ANOMALIE_CIN": "ANOMALIE_CIN",
    "PPE": "PPE",
}

# --- 5. Boucle Principale d'Exécution ---

if __name__ == '__main__':
    for code in filiales:
        print(f"\n==================== FILIALE {code} ====================")
        
        # Suppression des anciennes données. Pas besoin de transaction.atomic() autour du DELETE.
        count_anom, _ = Anomalie.objects.filter(FILIALE=f"BOA {code}").delete()
        print(f"🗑️ Suppression des anciens enregistrements : {count_anom} anomalies pour BOA {code}")

        # Chemin du fichier
        anom_path = os.path.join(chemin_base, f"anomalies_{code}.csv")

        # Importation des Anomalies
        if os.path.exists(anom_path):
            # *** UTILISER LA NOUVELLE FONCTION OPTIMISÉE ***
            importer_anom_optimise(anom_path, Anomalie, mapping_anom, code)
        else:
            print(f"⚠️ Fichier des anomalies manquant : {anom_path}")

    print("\n✨ Tous les imports d'anomalies sont terminés.")

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

FILIALES = ["SN",'NE','BF','MR','TG', 'CI','RDC']


CHEMIN_BASE = r"C:\Fiabilisation KYC\Python\data"
DELIMITEUR_CSV = ";" 
BULK_SIZE = 5000 

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


MODEL_FIELDS_CACHE = {}
def get_model_field_names(model):
    cached = MODEL_FIELDS_CACHE.get(model)
    if cached is not None:
        return cached
    fields = {f.name for f in model._meta.fields}
    MODEL_FIELDS_CACHE[model] = fields
    return fields

# --- 4. FONCTION D'IMPORTATION ---

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
                    model_fields = get_model_field_names(model)
                    for field, candidates in mapping.items():
                        if isinstance(candidates, str):
                            candidates = [candidates]
                        candidates = [normalize_header(c) for c in candidates]
                        if field in model_fields:
                            data[field] = pick_value(row_norm, candidates)
                    
                    # Nettoyage numérique
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

# --- 5. MAPPINGS ET MAIN ---
# (Tes mappings restent identiques)

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

    
