import csv
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import Agents   # Adapter selon ton projet


chemin_base = r"C:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\data"


def import_agents_from_folder(folder_path):
    # On filtre uniquement les fichiers agents_XX.csv
    csv_files = [
        f for f in os.listdir(folder_path)
        if f.lower().startswith("agents_") and f.lower().endswith(".csv")
    ]

    if not csv_files:
        print("⚠️ Aucun fichier agents_XX.csv trouvé.")
        return

    total_imported = 0

    for csv_file in csv_files:
        file_path = os.path.join(folder_path, csv_file)
        print(f"\n➡️ Import du fichier : {csv_file}")

        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter=';')

            agents_to_create = []

            for row in reader:
                filiale = row.get("FILIALE", "").strip()
                expl = row.get("EXPL", "").strip()
                agence = row.get("AGENCE", "").strip()
                agence_lib = row.get("AGENCELIB", "").strip()
                nom = row.get("NOM", "").strip()
                email = row.get("EMAIL", "").strip()

                # Pas d'insert si EXPL manquant
                if not expl:
                    continue

                # Éviter les doublons (expl + filiale)
                if Agents.objects.filter(expl=expl, filiale=filiale).exists():
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

            # Insertion en masse
            if agents_to_create:
                Agents.objects.bulk_create(agents_to_create)
                print(f"   ✓ {len(agents_to_create)} agents importés")

            total_imported += len(agents_to_create)

    print(f"\n🎉 Import total terminé ! Total agents importés : {total_imported}")


if __name__ == "__main__":
    import_agents_from_folder(chemin_base)
