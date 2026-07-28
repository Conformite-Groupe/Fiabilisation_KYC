import os
import csv
import django

                                                     
                                                                                                     
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

                                                         
from django.contrib.auth import get_user_model
                                 
                                                          
CHEMIN_CSV = r"C:\Fiabilisation KYC\Python\Fiabilisation_kyc\kyc\management\modify_user.csv"

def mettre_a_jour_utilisateurs():
    User = get_user_model()
    users_mis_a_jour = 0
    users_introuvables = 0

    if not os.path.exists(CHEMIN_CSV):
        print(f"❌ Fichier introuvable : {CHEMIN_CSV}")
        return

    try:
        with open(CHEMIN_CSV, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file, delimiter=';', quotechar='"')
            
            for row in reader:
                                       
                data = {k.strip(): v.strip() for k, v in row.items() if k}
                
                username = data.get('username')
                nouvelle_agence = data.get('agence')
                nouveau_code_expl = data.get('expl') 

                if not username:
                    continue

                try:
                                                
                    user = User.objects.get(username=username)
                    
                                 
                    user.agence = nouvelle_agence
                    user.code_expl = nouveau_code_expl
                    user.save(update_fields=['agence', 'code_expl'])
                    
                    users_mis_a_jour += 1
                    print(f"✅ Mis à jour : {username} -> Agence: {nouvelle_agence}, Expl: {nouveau_code_expl}")
                
                except User.DoesNotExist:
                    users_introuvables += 1
                    print(f"⚠️ Utilisateur non trouvé : {username}")

        print(f"\n--- TERMINE ---")
        print(f"Réussis : {users_mis_a_jour} | Introuvables : {users_introuvables}")

    except Exception as e:
        print(f"💥 Erreur : {str(e)}")

                             
if __name__ == "__main__":
    mettre_a_jour_utilisateurs()