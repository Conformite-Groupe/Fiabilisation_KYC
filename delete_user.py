import os
import django
import csv  # Import indispensable pour lire le fichier

# --- CONFIGURATION INITIALE DE DJANGO ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

# --- IMPORTS DE VOS MODÈLES ---
from accounts.models import ProfileV

# --- PARAMÈTRES ---
# Chemin vers votre fichier CSV (placez-le dans le même dossier ou spécifiez le chemin complet)
CSV_FILE_PATH = r"C:\Fiabilisation KYC\Python\data\delete_user.csv"

def supprimer_utilisateurs_depuis_csv(file_path):
    """
    Lit un fichier CSV et supprime les utilisateurs correspondants dans ProfileV.
    """
    if not os.path.exists(file_path):
        print(f"❌ Erreur : Le fichier '{file_path}' est introuvable.")
        return

    emails_traites = 0
    total_supprimés = 0

    print(f"🚀 Début du traitement du fichier : {file_path}")

    with open(file_path, mode='r', encoding='utf-8') as csvfile:
        # Utilisation de DictReader si votre CSV a un en-tête (ex: 'email')
        # Sinon, utilisez csv.reader(csvfile) pour un fichier sans en-tête
        reader = csv.reader(csvfile)
        
        for row in reader:
            if not row:
                continue
            
            # On récupère l'email (en supposant qu'il est dans la première colonne)
            email_a_chercher = row[0].strip()
            
            # Logique de filtrage (ici on cherche une correspondance exacte)
            # Si vous voulez garder le suffixe/alias, utilisez email__endswith=email_a_chercher
            queryset = ProfileV.objects.filter(email=email_a_chercher)
            
            count = queryset.count()
            if count > 0:
                resultat = queryset.delete()
                total_supprimés += resultat[0]
                print(f"✅ {email_a_chercher} : {count} enregistrement(s) supprimé(s).")
            else:
                print(f"⚠️ {email_a_chercher} : Aucun utilisateur trouvé.")
            
            emails_traites += 1

    print("--- Rapport Final ---")
    print(f"📧 Emails analysés dans le CSV : {emails_traites}")
    print(f"🗑️ Total des entrées supprimées en base : {total_supprimés}")


# --- EXÉCUTION DU SCRIPT ---
if __name__ == "__main__":
    supprimer_utilisateurs_depuis_csv(CSV_FILE_PATH)