from django.db import migrations, models


def seed_sidebar_access(apps, schema_editor):
    SidebarAccess = apps.get_model('kyc', 'SidebarAccess')
    organes = [
        'Directeur Agence',
        'Directeur de Zone',
        'Chargé Client',
        'Contrôle Permanent',
        'Directeur Réseau',
        'Contrôle Permanent Groupe',
        'Conformité',
        'Conformité Groupe',
        'PASS',
        'DSI',
        'GUEST',
        'Qualité',
        'DAI',
        'Risques',
    ]
    user_stat = ['Directeur Agence', 'Chargé Client']
    notation_org = ['Contrôle Permanent', 'PASS']
    conformite_org = ['Conformité', 'Conformité Groupe', 'PASS']
    admin_org = ['PASS', 'DSI', 'Conformité', 'Qualité', 'Contrôle Permanent',
                 'Conformité Groupe', 'Contrôle Permanent Groupe']
    for organe in organes:
        SidebarAccess.objects.update_or_create(
            organe=organe,
            defaults={
                'dashboard': True,
                'agents_notes': organe not in user_stat,
                'champs_non_renseignes': True,
                'clients_anomalie': True,
                'scoring_clients': True,
                'screening_kyc': True,
                'nouvelle_notation': organe in notation_org,
                'historique_notation': organe in notation_org,
                'ppe': organe in conformite_org,
                'comptes_specifiques': organe in conformite_org,
                'parametrage_utilisateurs': organe in ['PASS', 'DSI'],
                'regles_qualite': organe == 'PASS',
                'champs_kyc': organe == 'PASS',
                'documents_screening': organe == 'PASS',
                'rappels_scoring': organe == 'PASS',
                'pilotage': organe in admin_org,
                'audit': organe in admin_org,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0064_delete_anomalie'),
    ]

    operations = [
        migrations.CreateModel(
            name='SidebarAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('organe', models.CharField(choices=[('Directeur Agence', 'Directeur Agence'), ('Directeur de Zone', 'Directeur de Zone'), ('Chargé Client', 'Chargé Client'), ('Contrôle Permanent', 'Contrôle Permanent'), ('Directeur Réseau', 'Directeur Réseau'), ('Contrôle Permanent Groupe', 'Contrôle Permanent Groupe'), ('Conformité', 'Conformité'), ('Conformité Groupe', 'Conformité Groupe'), ('PASS', 'PASS'), ('DSI', 'DSI'), ('GUEST', 'GUEST'), ('Qualité', 'Qualité'), ('DAI', 'DAI'), ('Risques', 'Risques')], max_length=50, unique=True, verbose_name='Organe')),
                ('dashboard', models.BooleanField(default=True, verbose_name='Tableau de bord')),
                ('agents_notes', models.BooleanField(default=False, verbose_name='Agents notes')),
                ('champs_non_renseignes', models.BooleanField(default=True, verbose_name='Champs non-renseignes')),
                ('clients_anomalie', models.BooleanField(default=True, verbose_name='Clients en anomalie')),
                ('scoring_clients', models.BooleanField(default=True, verbose_name='Scoring clients')),
                ('screening_kyc', models.BooleanField(default=True, verbose_name='Screening KYC ID')),
                ('nouvelle_notation', models.BooleanField(default=False, verbose_name='Nouvelle notation')),
                ('historique_notation', models.BooleanField(default=False, verbose_name='Historique notation')),
                ('ppe', models.BooleanField(default=False, verbose_name='PPE')),
                ('comptes_specifiques', models.BooleanField(default=False, verbose_name='Comptes specifiques')),
                ('parametrage_utilisateurs', models.BooleanField(default=False, verbose_name='Parametrage utilisateurs')),
                ('regles_qualite', models.BooleanField(default=False, verbose_name='Regles de qualite')),
                ('champs_kyc', models.BooleanField(default=False, verbose_name='Champs KYC')),
                ('documents_screening', models.BooleanField(default=False, verbose_name='Documents Screening KYC ID')),
                ('rappels_scoring', models.BooleanField(default=False, verbose_name='Rappels Scoring')),
                ('pilotage', models.BooleanField(default=False, verbose_name='Pilotage')),
                ('audit', models.BooleanField(default=False, verbose_name='Audit')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Acces sidebar (par organe)',
                'verbose_name_plural': 'Acces sidebar (par organe)',
                'ordering': ['organe'],
            },
        ),
        migrations.RunPython(seed_sidebar_access, migrations.RunPython.noop),
    ]
