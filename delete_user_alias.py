import os
import django

# --- CONFIGURATION INITIALE DE DJANGO ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

# --- IMPORTS DE VOS MODÈLES ---
from accounts.models import ProfileV

def supprimer_utilisateurs_par_alias(alias):
    """
    Supprime tous les profils dont l'email se termine par l'alias spécifié.
    """
    print(f"🚀 Recherche des utilisateurs avec l'alias : {alias}")

    # Utilisation du filtre __endswith pour cibler le suffixe
    queryset = ProfileV.objects.filter(email__endswith=alias)
    
    nombre_a_supprimer = queryset.count()

    if nombre_a_supprimer > 0:
        # Confirmation avant suppression (optionnel mais recommandé)
        reponse = input(f"⚠️ {nombre_a_supprimer} utilisateurs trouvés. Confirmer la suppression ? (y/n): ")
        
        if reponse.lower() == 'y':
            # .delete() renvoie un tuple (nombre total, détails par modèle)
            total_supprimes, details = queryset.delete()
            print(f"✅ Suppression terminée. {total_supprimes} enregistrements supprimés.")
        else:
            print("❌ Opération annulée.")
    else:
        print(f"⚠️ Aucun utilisateur trouvé avec l'alias {alias}.")

# --- EXÉCUTION DU SCRIPT ---
if __name__ == "__main__":
    ALIAS_CIBLE = "@boa-rdc.com"
    supprimer_utilisateurs_par_alias(ALIAS_CIBLE)