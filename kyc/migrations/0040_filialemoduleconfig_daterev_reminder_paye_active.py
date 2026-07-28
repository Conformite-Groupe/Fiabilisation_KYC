                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0039_alter_appreciationconfig_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='filialemoduleconfig',
            name='daterev_reminder_paye_active',
            field=models.BooleanField(default=False, help_text='Si décoché, les chargés de cette filiale ne reçoivent pas les rappels DATEREV automatiques.', verbose_name='Module Rappels DATEREV PAYE actif'),
        ),
    ]
