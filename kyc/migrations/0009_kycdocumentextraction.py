                                                

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kyc', '0008_remove_dataqualitycondition_is_field_comparison_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='KycDocumentExtraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_type', models.CharField(choices=[('piece_identite', "Piece d'identite"), ('passeport', 'Passeport')], max_length=30)),
                ('uploaded_file', models.FileField(upload_to='document_extraction/')),
                ('original_filename', models.CharField(blank=True, max_length=255)),
                ('nom', models.CharField(blank=True, max_length=120)),
                ('prenom', models.CharField(blank=True, max_length=120)),
                ('numero_document', models.CharField(blank=True, max_length=120)),
                ('date_naissance', models.CharField(blank=True, max_length=120)),
                ('date_expiration', models.CharField(blank=True, max_length=120)),
                ('nationalite', models.CharField(blank=True, max_length=120)),
                ('numero_identification_nationale', models.CharField(blank=True, max_length=120)),
                ('lieu_naissance', models.CharField(blank=True, max_length=120)),
                ('adresse', models.CharField(blank=True, max_length=255)),
                ('extracted_text', models.TextField(blank=True)),
                ('extraction_warnings', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['document_type'], name='kyc_kycdocu_documen_62be4b_idx'), models.Index(fields=['numero_document'], name='kyc_kycdocu_numero__6f9b4a_idx'), models.Index(fields=['nom'], name='kyc_kycdocu_nom_02b6f7_idx'), models.Index(fields=['prenom'], name='kyc_kycdocu_prenom_a06fec_idx'), models.Index(fields=['date_naissance'], name='kyc_kycdocu_date_na_aa033a_idx'), models.Index(fields=['date_expiration'], name='kyc_kycdocu_date_ex_7c2272_idx'), models.Index(fields=['nationalite'], name='kyc_kycdocu_nationa_0ab772_idx')],
            },
        ),
    ]
