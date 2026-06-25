from django.db import migrations


def backfill_rule_filiale(apps, schema_editor):
    DataQualityRule = apps.get_model('kyc', 'DataQualityRule')
    for rule in DataQualityRule.objects.select_related('created_by').filter(filiale=''):
        user_filiale = (getattr(rule.created_by, 'filiale', '') or '').strip() if rule.created_by_id else ''
        if user_filiale:
            rule.filiale = user_filiale
            rule.save(update_fields=['filiale'])


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0020_dataqualityrule_filiale'),
    ]

    operations = [
        migrations.RunPython(backfill_rule_filiale, migrations.RunPython.noop),
    ]
