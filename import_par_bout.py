# =====================================================
# 0. IMPORT PAR BOUT 

# Pour une filiale ajouter "--filiales XX"
# =====================================================



# 1. Anomalies 

$env:KYC_ONLY="anomalies"
python import_premier.py



# 2. Scoring 

$env:KYC_ONLY="daterev"
python import_premier.py --filiales TG


# 3.Taux d'évolution des filiales


$env:KYC_ONLY="taux_filiales"
python import_premier.py


