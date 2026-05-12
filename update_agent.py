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