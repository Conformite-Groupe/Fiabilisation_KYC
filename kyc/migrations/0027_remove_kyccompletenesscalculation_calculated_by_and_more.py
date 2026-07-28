                                               

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0026_backfill_scorer_fields_from_daterev'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='kyccompletenesscalculation',
            name='calculated_by',
        ),
        migrations.DeleteModel(
            name='KycCompletenessFieldConfig',
        ),
        migrations.RenameIndex(
            model_name='kycdocumentmatchjob',
            new_name='kyc_kycdocu_status_dca39e_idx',
            old_name='kyc_kycdocu_status_9aab5d_idx',
        ),
        migrations.RenameIndex(
            model_name='kycdocumentmatchjob',
            new_name='kyc_kycdocu_created_5286cf_idx',
            old_name='kyc_kycdocu_created_58ccff_idx',
        ),
        migrations.DeleteModel(
            name='KycCompletenessCalculation',
        ),
    ]
