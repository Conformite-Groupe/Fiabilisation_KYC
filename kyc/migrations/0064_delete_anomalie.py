                                                

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0063_alter_emailreminderconfig_options_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Anomalie',
        ),
    ]
