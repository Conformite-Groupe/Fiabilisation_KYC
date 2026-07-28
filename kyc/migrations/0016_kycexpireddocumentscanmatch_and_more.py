                                                

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0015_alter_kycdocumentmatchsettings_birth_date_weight_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='KycExpiredDocumentScanMatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_code', models.CharField(blank=True, max_length=200)),
                ('idp', models.CharField(blank=True, max_length=200)),
                ('filiale', models.CharField(blank=True, max_length=200)),
                ('agence', models.CharField(blank=True, max_length=200)),
                ('old_validity_date', models.CharField(blank=True, max_length=120)),
                ('document_validity_date', models.CharField(blank=True, max_length=120)),
                ('match_rate', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)])),
                ('status', models.CharField(choices=[('a_valider', 'A valider'), ('valide', 'Valide'), ('rejete', 'Rejete')], default='a_valider', max_length=20)),
                ('scan_date', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(blank=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expired_document_matches', to='kyc.kyc_pp')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expired_kyc_matches', to='kyc.kycdocumentextraction')),
            ],
            options={
                'verbose_name': 'Correspondance document expire KYC',
                'verbose_name_plural': 'Correspondances documents expires KYC',
                'ordering': ['-scan_date'],
                'indexes': [models.Index(fields=['status'], name='kyc_kycexpi_status_bf7e17_idx'), models.Index(fields=['client_code'], name='kyc_kycexpi_client__c6bc40_idx'), models.Index(fields=['filiale', 'agence'], name='kyc_kycexpi_filiale_eb56ba_idx'), models.Index(fields=['scan_date'], name='kyc_kycexpi_scan_da_000c77_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='kycexpireddocumentscanmatch',
            constraint=models.UniqueConstraint(fields=('client', 'document'), name='unique_expired_kyc_document_match'),
        ),
    ]
