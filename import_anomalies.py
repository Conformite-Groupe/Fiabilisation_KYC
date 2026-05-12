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