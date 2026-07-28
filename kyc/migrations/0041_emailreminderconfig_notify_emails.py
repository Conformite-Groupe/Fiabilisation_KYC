                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0040_filialemoduleconfig_daterev_reminder_paye_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailreminderconfig',
            name='notify_emails',
            field=models.TextField(blank=True, default='', help_text="Destinataires du rapport d'exécution des tâches quotidiennes, séparés par des virgules / points-virgules / sauts de ligne.", verbose_name='Emails de supervision (rapport quotidien)'),
        ),
    ]
