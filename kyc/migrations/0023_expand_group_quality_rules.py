from django.db import migrations


FILIALES = [
    'BOA NE', 'BOA CI', 'BOA TG', 'BOA SN', 'BOA ML', 'BOA BF', 'BOA BJ',
    'BOA RDC', 'CG', 'BCB', 'BOA MR', 'BOA MG', 'BOA UG', 'BOA TZ',
    'BOA RW', 'BOA KE', 'BOA FR', 'BOA KM', 'BOA GH',
]


def expand_group_rules(apps, schema_editor):
    DataQualityRule = apps.get_model('kyc', 'DataQualityRule')
    replacement = f"|{'|'.join(FILIALES)}|"
    for rule in DataQualityRule.objects.filter(filiale='|BOA Group|'):
        rule.filiale = replacement
        rule.save(update_fields=['filiale'])


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0022_dataqualityrule_multi_filiales'),
    ]

    operations = [
        migrations.RunPython(expand_group_rules, migrations.RunPython.noop),
    ]
