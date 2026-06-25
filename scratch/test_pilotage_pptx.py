import sys
import os
# Add current directory to sys.path
sys.path.append(os.getcwd())

import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.pilotage_exports import export_pilotage_pptx

# Mock data
scope_data = {
    "scope": "groupe",
    "selected_filiale": ""
}
summary = {
    "threshold": 90.0,
    "completeness_rate": 87.5,
    "quality_rate": 92.1,
    "low_completeness_count": 3,
    "low_quality_count": 1
}
completeness_rows = [
    {"type": "PP", "filiale": "BOA BENIN", "field_name": "NUMID", "field_label": "Numéro d'identification", "total_clients": 1500, "missing_count": 250, "rate": 83.3, "is_below_threshold": True},
    {"type": "PM", "filiale": "BOA SENEGAL", "field_name": "NUMERO_FISCAL", "field_label": "Numéro NIF", "total_clients": 1200, "missing_count": 180, "rate": 85.0, "is_below_threshold": True},
    {"type": "PP", "filiale": "BOA BENIN", "field_name": "DATNAIS", "field_label": "Date de naissance", "total_clients": 1500, "missing_count": 120, "rate": 92.0, "is_below_threshold": False},
]
quality_rows = [
    {"type": "PP", "scope_label": "BOA BENIN", "rule_name": "CIN invalide", "field_label": "NUMID", "total_clients": 1500, "fail_count": 200, "rate": 86.7, "is_below_threshold": True},
    {"type": "PM", "scope_label": "BOA SENEGAL", "rule_name": "NIF manquant", "field_label": "NUMERO_FISCAL", "total_clients": 1200, "fail_count": 50, "rate": 95.8, "is_below_threshold": False},
]

print("Calling export_pilotage_pptx...")
response = export_pilotage_pptx(scope_data, summary, completeness_rows, quality_rows)
print("Response content type:", response['Content-Type'])
print("Response disposition:", response['Content-Disposition'])

# Write response content to a test PPTX file
output_path = "scratch/test_output.pptx"
with open(output_path, "wb") as f:
    f.write(response.content)
print(f"File written to {output_path} successfully!")
