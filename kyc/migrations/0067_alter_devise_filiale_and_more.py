
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0066_sync_sidebaraccess_profile_organs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devise',
            name='filiale',
            field=models.CharField(choices=[('BOA BJ', 'BOA BJ')], default='', max_length=10),
        ),
        migrations.AlterField(
            model_name='filialemoduleconfig',
            name='filiale',
            field=models.CharField(choices=[('BOA BJ', 'BOA BJ')], max_length=15, unique=True, verbose_name='Filiale/Pays'),
        ),
        migrations.AlterField(
            model_name='kycdocumenttype',
            name='filiale',
            field=models.CharField(blank=True, choices=[('BOA BJ', 'BOA BJ')], default='', max_length=15, verbose_name='Filiale/Pays'),
        ),
    ]
