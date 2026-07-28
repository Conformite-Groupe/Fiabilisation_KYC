                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0013_kycdocumentmatchsettings_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='birth_place_weight',
            field=models.PositiveSmallIntegerField(default=10, verbose_name='Poids lieu de naissance'),
        ),
    ]
