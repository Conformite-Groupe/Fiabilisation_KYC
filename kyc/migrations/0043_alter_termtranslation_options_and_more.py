                                               

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0042_termtranslation'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='termtranslation',
            options={'ordering': ['terme_fr'], 'verbose_name': 'Traduction de terme (glossaire)', 'verbose_name_plural': 'Glossaire des traductions FR → EN'},
        ),
        migrations.RemoveField(
            model_name='termtranslation',
            name='domaine',
        ),
    ]
