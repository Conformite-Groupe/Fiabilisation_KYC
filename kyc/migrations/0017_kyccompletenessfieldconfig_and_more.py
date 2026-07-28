                                                

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kyc', '0016_kycexpireddocumentscanmatch_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='KycCompletenessFieldConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(blank=True, help_text='Laisser vide pour une configuration Groupe par defaut', max_length=200)),
                ('applicability', models.CharField(choices=[('PP', 'Client PP'), ('PM', 'Client PM')], max_length=3)),
                ('field_name', models.CharField(max_length=100)),
                ('is_critical', models.BooleanField(default=True)),
                ('show_on_non_rens', models.BooleanField(default=True)),
                ('exclusion_field_name', models.CharField(blank=True, max_length=100)),
                ('exclusion_expression', models.CharField(blank=True, max_length=255)),
                ('active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Parametrage completude KYC',
                'verbose_name_plural': 'Parametrages completude KYC',
                'ordering': ['filiale', 'applicability', 'field_name'],
                'unique_together': {('filiale', 'applicability', 'field_name')},
            },
        ),
        migrations.CreateModel(
            name='KycCompletenessCalculation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(max_length=200)),
                ('applicability', models.CharField(choices=[('PP', 'Client PP'), ('PM', 'Client PM')], max_length=3)),
                ('scope_type', models.CharField(choices=[('FILIALE', 'Filiale'), ('AGENCE', 'Agence'), ('EXPL', 'Agent / Exploitant')], max_length=10)),
                ('agence', models.CharField(blank=True, max_length=200)),
                ('expl', models.CharField(blank=True, max_length=200)),
                ('field_name', models.CharField(blank=True, max_length=100)),
                ('is_global', models.BooleanField(default=False)),
                ('total_clients', models.PositiveIntegerField(default=0)),
                ('compliant_clients', models.PositiveIntegerField(default=0)),
                ('incomplete_clients', models.PositiveIntegerField(default=0)),
                ('excluded_clients', models.PositiveIntegerField(default=0)),
                ('completeness_rate', models.FloatField(default=0)),
                ('calculated_at', models.DateTimeField(auto_now_add=True)),
                ('calculated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Resultat calcul completude KYC',
                'verbose_name_plural': 'Resultats calcul completude KYC',
                'ordering': ['-calculated_at', 'filiale', 'applicability', 'scope_type', 'agence', 'expl', 'field_name'],
                'indexes': [models.Index(fields=['filiale', 'applicability', 'scope_type', 'agence', 'expl', 'is_global'], name='kyc_kyccomp_filiale_801479_idx'), models.Index(fields=['calculated_at'], name='kyc_kyccomp_calcula_41c3f6_idx')],
            },
        ),
    ]
