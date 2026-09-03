
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0068_add_exact_word_quality_operators'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devise',
            name='filiale',
            field=models.CharField(choices=[('BOA SN', 'BOA SN')], default='', max_length=10),
        ),
        migrations.AlterField(
            model_name='filialemoduleconfig',
            name='filiale',
            field=models.CharField(choices=[('BOA SN', 'BOA SN')], max_length=15, unique=True, verbose_name='Filiale/Pays'),
        ),
        migrations.AlterField(
            model_name='kycdocumenttype',
            name='filiale',
            field=models.CharField(blank=True, choices=[('BOA SN', 'BOA SN')], default='', max_length=15, verbose_name='Filiale/Pays'),
        ),
    ]
