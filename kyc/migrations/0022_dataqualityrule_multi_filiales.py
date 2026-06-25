from django.db import migrations, models


def normalize_rule_filiales(apps, schema_editor):
    DataQualityRule = apps.get_model('kyc', 'DataQualityRule')
    for rule in DataQualityRule.objects.exclude(filiale=''):
        raw = (rule.filiale or '').strip()
        if not raw or (raw.startswith('|') and raw.endswith('|')):
            continue
        if ',' in raw:
            values = [value.strip() for value in raw.split(',') if value.strip()]
        else:
            values = [raw]
        if values:
            rule.filiale = f"|{'|'.join(dict.fromkeys(values))}|"
            rule.save(update_fields=['filiale'])


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0021_backfill_dataqualityrule_filiale'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataqualityrule',
            name='filiale',
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(normalize_rule_filiales, migrations.RunPython.noop),
    ]
