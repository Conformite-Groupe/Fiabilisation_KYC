                                                

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kyc', '0004_delete_taux_filiale'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataQualityRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('applicability', models.CharField(choices=[('PP', 'Client PP'), ('PM', 'Client PM')], max_length=3)),
                ('field_name', models.CharField(choices=[('CODAPE', 'CODAPE'), ('IDP', 'IDP'), ('PAYNAIS', 'PAYNAIS'), ('PROFESSION', 'PROFESSION'), ('ADRESSE', 'ADRESSE'), ('PAYS_RESID', 'PAYS_RESID'), ('NUMID', 'NUMID'), ('SALAIRE', 'SALAIRE'), ('DATVALID', 'DATVALID'), ('TEL', 'TEL'), ('DATOUV', 'DATOUV'), ('PPE', 'PPE'), ('DEVISE', 'DEVISE'), ('RESID', 'RESID'), ('CODAPE', 'CODAPE'), ('AGEC', 'AGEC'), ('IDM', 'IDM'), ('RCSNO', 'RCSNO'), ('CAPITAL', 'CAPITAL'), ('CA', 'CA'), ('DATOUV', 'DATOUV'), ('TEL', 'TEL'), ('DEVISE', 'DEVISE'), ('RESID', 'RESID')], max_length=100)),
                ('control_type', models.CharField(choices=[('existence', 'Existence de données'), ('min_length', 'Nombre minimal de caractères'), ('max_length', 'Nombre maximal de caractères'), ('min_value', 'Valeur minimale'), ('max_value', 'Valeur maximale'), ('expired_document', 'Document expiré'), ('codape_agec_match', 'Correspondance CODAPE / AGEC')], max_length=50)),
                ('parameter', models.CharField(blank=True, help_text='Seuil, longueur ou valeur de référence', max_length=200)),
                ('description', models.TextField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
