                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_auditevent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditevent',
            name='category',
            field=models.CharField(choices=[('CONNEXION', 'Connexion'), ('HABILITATION', 'Habilitation'), ('IMPORT', 'Import de donnees'), ('DONNEES', 'Mise a jour de donnees'), ('CONFIG', 'Parametrage'), ('EXPORT', 'Export'), ('SCREENING', 'Screening KYC ID'), ('NOTATION', 'Notation'), ('SECURITE', 'Securite')], db_index=True, default='DONNEES', max_length=20),
        ),
    ]
