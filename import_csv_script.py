import csv
import os
import django
from django.db import transaction
import chardet

                                                       
               
                                                       
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Agents


                                                       
            
                                                       
chemin_base = r"C:\Fiabilisation KYC\Python\data"
BULK_SIZE = 5000


                                                       
                    
                                                       
def detect_encoding(file_path):
    with open(file_path, "rb") as f:
        result = chardet.detect(f.read(100000))
        return result["encoding"]


                                                       
               
                                                       
def import_agents_from_folder(folder_path):

    csv_files = [
        f for f in os.listdir(folder_path)
        if f.lower().startswith("agent_") and f.lower().endswith(".csv")
    ]

    if not csv_files:
        print("⚠️ Aucun fichier agent_XX.csv trouvé.")
        return

    total_imported = 0
    total_skipped_expl = 0
    total_skipped_duplicate = 0
    total_lines = 0

    existing_agents = set(
        Agents.objects.values_list("expl", "filiale")
    )

    for csv_file in csv_files:

        file_path = os.path.join(folder_path, csv_file)

        print(f"\n➡️ Import du fichier : {csv_file}")

        encoding = detect_encoding(file_path)

        with open(file_path, mode="r", encoding=encoding, errors="replace") as file:

            reader = csv.DictReader(file, delimiter=";")

            agents_to_create = []

            for row in reader:

                total_lines += 1

                filiale = (row.get("FILIALE") or "").strip()
                expl = (row.get("EXPL") or "").strip()
                agence = (row.get("AGENCE") or "").strip()
                agence_lib = (row.get("AGENCELIB") or "").strip()
                nom = (row.get("NOM") or "").strip()
                email = (row.get("EMAIL") or "").strip()

                                  
                if not expl:
                    total_skipped_expl += 1
                    continue

                         
                if (expl, filiale) in existing_agents:
                    total_skipped_duplicate += 1
                    continue

                agent = Agents(
                    filiale=filiale or None,
                    expl=expl or None,
                    agence=agence or None,
                    agence_lib=agence_lib or None,
                    nom=nom or None,
                    email=email or None,
                )

                agents_to_create.append(agent)
                existing_agents.add((expl, filiale))

                if len(agents_to_create) >= BULK_SIZE:
                    Agents.objects.bulk_create(agents_to_create)
                    total_imported += len(agents_to_create)
                    print(f"   ✓ {len(agents_to_create)} agents importés")
                    agents_to_create.clear()

            if agents_to_create:
                Agents.objects.bulk_create(agents_to_create)
                total_imported += len(agents_to_create)
                print(f"   ✓ {len(agents_to_create)} agents importés")

    print("\n==============================")
    print("📊 RAPPORT IMPORT")
    print("==============================")
    print(f"Lignes CSV lues : {total_lines}")
    print(f"Agents importés : {total_imported}")
    print(f"EXPL manquant : {total_skipped_expl}")
    print(f"Doublons ignorés : {total_skipped_duplicate}")
    print("==============================\n")


                                                       
           
                                                       
if __name__ == "__main__":

    with transaction.atomic():
        import_agents_from_folder(chemin_base)