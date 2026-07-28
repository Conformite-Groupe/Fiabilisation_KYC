                                               

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0003_daterev_unique_client_constraint'),
    ]

    operations = [
        migrations.DeleteModel(
            name='TAUX_FILIALE',
        ),
    ]
