                                               

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0055_alter_dataqualitycondition_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TauxQualite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(blank=True, max_length=50, null=True)),
                ('agence', models.CharField(blank=True, max_length=50, null=True)),
                ('expl', models.CharField(blank=True, max_length=50, null=True)),
                ('applicability', models.CharField(max_length=2)),
                ('rate', models.FloatField(default=0)),
                ('ok_count', models.IntegerField(default=0)),
                ('total', models.IntegerField(default=0)),
                ('date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='kyc_pp',
            index=models.Index(fields=['FILIALE', 'AGENCE', 'EXPL'], name='kyc_pp_scope_idx'),
        ),
        migrations.AddIndex(
            model_name='tauxqualite',
            index=models.Index(fields=['date', 'applicability', 'filiale', 'agence', 'expl'], name='kyc_tauxqua_date_c38c82_idx'),
        ),
        migrations.AddConstraint(
            model_name='tauxqualite',
            constraint=models.UniqueConstraint(fields=('filiale', 'agence', 'expl', 'applicability', 'date'), name='uniq_tauxqualite_scope_jour'),
        ),
    ]
