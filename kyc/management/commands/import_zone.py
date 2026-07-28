import os
import django
import csv
from django.db import transaction
from django.core.management.base import BaseCommand
from pathlib import Path

                                          
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
    django.setup()

from accounts.models import Zone


class Command(BaseCommand):
    help = "Importe les fichiers de zones avec ZONE, AGENCE et FILIALE"

    def handle(self, *args, **kwargs):
        dossier = Path(
            r"C:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\data")
        codes_pays = ["CI", "SN", "BF"]

        for code in codes_pays:
            fichier = dossier / f'zone_{code}.csv'

            if not fichier.exists():
                self.stdout.write(self.style.WARNING(f"Fichier manquant : {fichier.name}"))
                continue

            self.stdout.write(f"Lecture de : {fichier.name}...")

            objs = []
            try:
                with open(fichier, newline='', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f, delimiter=';')

                    for row in reader:
                                                                         
                        row_clean = {k.strip().upper(): v.strip() for k, v in row.items() if k}

                        zone_val = row_clean.get('ZONE')
                        agence_val = row_clean.get('AGENCE')
                        filiale_val = row_clean.get('FILIALE')

                        directeur = row_clean.get('DIRECTEUR')

                        if zone_val or agence_val:
                            objs.append(Zone(
                                zone=zone_val,
                                agence=agence_val,

                                filiale=filiale_val,
                                directeur = directeur
                            ))

                if objs:
                    with transaction.atomic():
                        Zone.objects.bulk_create(objs, batch_size=1000)
                    self.stdout.write(self.style.SUCCESS(f"✅ Importation réussie : {len(objs)} lignes pour {code}"))
                else:
                    self.stdout.write(self.style.WARNING(f"⚠️ Aucune donnée trouvée dans {fichier.name}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Erreur sur {code} : {str(e)}"))