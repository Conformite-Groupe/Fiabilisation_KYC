                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0061_qualityfluxconfig_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='kyc_pm',
            index=models.Index(fields=['RESID'], name='kyc_pm_resid_idx'),
        ),
        migrations.AddIndex(
            model_name='kyc_pm',
            index=models.Index(fields=['DEVISE'], name='kyc_pm_devise_idx'),
        ),
        migrations.AddIndex(
            model_name='kyc_pp',
            index=models.Index(fields=['PPE'], name='kyc_pp_ppe_idx'),
        ),
        migrations.AddIndex(
            model_name='kyc_pp',
            index=models.Index(fields=['RESID'], name='kyc_pp_resid_idx'),
        ),
        migrations.AddIndex(
            model_name='kyc_pp',
            index=models.Index(fields=['DEVISE'], name='kyc_pp_devise_idx'),
        ),
    ]
