                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0030_kycdocumenttype'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumenttype',
            name='filiale',
            field=models.CharField(blank=True, choices=[('BOA NE', 'BOA NE'), ('BOA CI', 'BOA CI'), ('BOA TG', 'BOA TG'), ('BOA SN', 'BOA SN'), ('BOA ML', 'BOA ML'), ('BOA BF', 'BOA BF'), ('BOA BJ', 'BOA BJ'), ('BOA RDC', 'RDC'), ('LCB', 'LCB'), ('BCB', 'BCB'), ('BOA MR', 'BOA MR'), ('BOA MG', 'BOA MG'), ('BOA UG', 'BOA UG'), ('BOA TZ', 'BOA TZ'), ('BOA RW', 'BOA RW'), ('BOA KE', 'BOA KE'), ('BOA FR', 'BOA FR'), ('BOA KM', 'BOA KM'), ('BOA GH', 'BOA GH'), ('BOA Group', 'BOA Group')], default='', max_length=15, verbose_name='Filiale/Pays'),
        ),
        migrations.AlterField(
            model_name='kycdocumenttype',
            name='code',
            field=models.CharField(max_length=50, verbose_name='Code technique'),
        ),
        migrations.AlterUniqueTogether(
            name='kycdocumenttype',
            unique_together={('code', 'filiale')},
        ),
    ]
