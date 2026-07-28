                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0010_kycdocumentextraction_import_batch_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumentextraction',
            name='origine_revenu',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='kycdocumentextraction',
            name='pays_naissance',
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
