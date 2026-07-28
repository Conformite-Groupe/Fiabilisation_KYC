                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0031_kycdocumenttype_filiale_alter_kycdocumenttype_code_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='kycdocumenttype',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='kycdocumentextraction',
            name='client_type',
            field=models.CharField(choices=[('pp', 'Particuliers (PP)'), ('pm', 'Entreprises (PM)')], default='pp', max_length=10, verbose_name='Type de client'),
        ),
        migrations.AddField(
            model_name='kycdocumenttype',
            name='client_type',
            field=models.CharField(choices=[('pp', 'Particuliers (PP)'), ('pm', 'Entreprises (PM)')], default='pp', max_length=10, verbose_name='Type de client'),
        ),
        migrations.AlterUniqueTogether(
            name='kycdocumenttype',
            unique_together={('code', 'filiale', 'client_type')},
        ),
        migrations.AddIndex(
            model_name='kycdocumentextraction',
            index=models.Index(fields=['client_type'], name='kyc_kycdocu_client__5496a8_idx'),
        ),
    ]
