import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import (
    Agents, Notation, Historique,
    Kyc_pm, Kyc_pp, Anomalie,
    TauxEvolution, TauxEvolution_filiale,
    DATEREV, TAUX_FILIALE
)

from accounts.models import(ProfileV)

models = [
   ProfileV
   # DATEREV, TAUX_FILIALE
]


#models = [
#    Agents, Notation, Historique,
#    Kyc_pm, Kyc_pp, Anomalie,
#    TauxEvolution, TauxEvolution_filiale,
#    DATEREV, TAUX_FILIALE
#]
#
for model in models:
    count = model.objects.count()
    model.objects.all().delete()
    print(f"{model.__name__} supprimé ({count} enregistrements)")

    
