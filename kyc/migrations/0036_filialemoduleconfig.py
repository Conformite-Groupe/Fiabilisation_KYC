                                               

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0035_alter_dataqualitycondition_field_name_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FilialeModuleConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(choices=[('BOA NE', 'BOA NE'), ('BOA CI', 'BOA CI'), ('BOA TG', 'BOA TG'), ('BOA SN', 'BOA SN'), ('BOA ML', 'BOA ML'), ('BOA BF', 'BOA BF'), ('BOA BJ', 'BOA BJ'), ('BOA RDC', 'RDC'), ('LCB', 'LCB'), ('BCB', 'BCB'), ('BOA MR', 'BOA MR'), ('BOA MG', 'BOA MG'), ('BOA UG', 'BOA UG'), ('BOA TZ', 'BOA TZ'), ('BOA RW', 'BOA RW'), ('BOA KE', 'BOA KE'), ('BOA FR', 'BOA FR'), ('BOA KM', 'BOA KM'), ('BOA GH', 'BOA GH'), ('BOA Group', 'BOA Group')], max_length=15, unique=True, verbose_name='Filiale/Pays')),
                ('screening_kyc_paye_active', models.BooleanField(default=False, verbose_name='Module Screening KYC PAYE actif')),
            ],
            options={
                'verbose_name': 'Configuration Module Filiale',
                'verbose_name_plural': 'Configurations Modules Filiales',
            },
        ),
    ]
