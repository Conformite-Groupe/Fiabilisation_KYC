import os
import django
import csv                                             

                                          
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

                                
from accounts.models import ProfileV

                    
                                                                                               
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
                                                                           
                                                                          
        reader = csv.reader(csvfile)
        
        for row in reader:
            if not row:
                continue
            
                                                                                   
            email_a_chercher = row[0].strip()
            
                                                                            
                                                                                               
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


                             
if __name__ == "__main__":
    supprimer_utilisateurs_depuis_csv(CSV_FILE_PATH)