import csv
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from Fiabilisation_kyc.settings import AUTH_USER_MODEL


class Command(BaseCommand):
    help = 'Crée des utilisateurs en masse depuis un fichier CSV'

    def add_arguments(self, parser):
        parser.add_argument('bulk_users', type=str, help='/management')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['bulk_users']
        User = get_user_model()

        with open(csv_file, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            users_created = 0

            for row in reader:
       
                username = row.get('username')
                first_name = row.get('first_name')
                last_name = row.get('last_name')
                organe = row.get('organe')
                téléphone = row.get('téléphone')
                organe = row.get('agence')
                code_expl = row.get('code_expl')
                password1 = row.get('password1')

                # Créez l'utilisateur avec les champs personnalisés
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'organe': organe,
                         'agence': organe ,
                          'organe': organe,
                        'téléphone': téléphone,
                    }
                )
                if created:
                    user.set_password(password1)  # Définit le mot de passe
                    user.save()
                    users_created += 1

        self.stdout.write(self.style.SUCCESS(f"{users_created} utilisateurs créés avec succès."))

