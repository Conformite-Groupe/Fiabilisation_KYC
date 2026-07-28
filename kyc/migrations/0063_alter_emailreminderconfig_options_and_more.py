                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0062_kyc_pm_kyc_pm_resid_idx_kyc_pm_kyc_pm_devise_idx_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='emailreminderconfig',
            options={'verbose_name': 'Configuration Rappel Scoring', 'verbose_name_plural': 'Configurations Rappel Scoring'},
        ),
        migrations.AlterField(
            model_name='emailreminderconfig',
            name='days_before',
            field=models.IntegerField(default=30, help_text='Inclure les clients dont la date de revue (Scoring) expire dans ce nombre de jours', verbose_name='Jours avant expiration'),
        ),
        migrations.AlterField(
            model_name='filialemoduleconfig',
            name='daterev_reminder_paye_active',
            field=models.BooleanField(default=False, help_text='Si décoché, les chargés de cette filiale ne reçoivent pas les rappels Scoring automatiques.', verbose_name='Module Rappels Scoring PAYE actif'),
        ),
    ]
