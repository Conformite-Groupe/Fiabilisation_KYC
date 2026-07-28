                                               

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0043_alter_termtranslation_options_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumentextraction',
            name='extraction_status',
            field=models.CharField(choices=[('pending', 'En attente OCR'), ('processing', 'OCR en cours'), ('done', 'Traite'), ('failed', 'Echec OCR')], db_index=True, default='done', max_length=20),
        ),
        migrations.AddField(
            model_name='kycdocumentextraction',
            name='file_hash',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.CreateModel(
            name='KycDocumentOcrJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('import_batch', models.CharField(db_index=True, max_length=120)),
                ('mode', models.CharField(choices=[('files', 'Fichiers individuels'), ('grouped_pdf', 'PDF groupe')], default='files', max_length=20)),
                ('client_type', models.CharField(choices=[('pp', 'Particuliers (PP)'), ('pm', 'Entreprises (PM)')], default='pp', max_length=10)),
                ('document_type', models.CharField(blank=True, default='', max_length=50)),
                ('pages_per_document', models.PositiveSmallIntegerField(default=1)),
                ('grouped_source_file', models.CharField(blank=True, default='', help_text='Chemin relatif du PDF groupe (mode grouped_pdf).', max_length=255)),
                ('grouped_original_name', models.CharField(blank=True, default='', max_length=255)),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('running', 'En cours'), ('completed', 'Termine'), ('failed', 'Echec')], db_index=True, default='pending', max_length=20)),
                ('progress_current', models.PositiveIntegerField(default=0)),
                ('progress_total', models.PositiveIntegerField(default=0)),
                ('done_count', models.PositiveIntegerField(default=0)),
                ('failed_count', models.PositiveIntegerField(default=0)),
                ('message', models.CharField(blank=True, max_length=255)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Job OCR documents KYC',
                'verbose_name_plural': 'Jobs OCR documents KYC',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['status', 'created_at'], name='kyc_kycdocu_status_9c57e4_idx'), models.Index(fields=['import_batch'], name='kyc_kycdocu_import__65b0b8_idx')],
            },
        ),
    ]
