                                               

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0050_seed_match_validator_roles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='kycmatchdecision',
            name='status',
            field=models.CharField(choices=[('pending', 'A valider'), ('validated', 'Valide'), ('rejected', 'Rejete')], db_index=True, default='pending', max_length=20),
        ),
    ]
