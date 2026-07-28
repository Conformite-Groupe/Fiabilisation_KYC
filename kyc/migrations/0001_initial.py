                                               

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Agents',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(blank=True, choices=[('BOA NE', 'BOA NE'), ('BOA CI', 'BOA CI'), ('BOA TG', 'BOA TG'), ('BOA SN', 'BOA SN'), ('BOA ML', 'BOA ML'), ('BOA BF', 'BOA BF'), ('BOA BJ', 'BOA BJ'), ('BOA RDC', 'RDC'), ('LCB', 'LCB'), ('BCB', 'BCB'), ('BOA MR', 'BOA MR'), ('BOA MG', 'BOA MG'), ('BOA UG', 'BOA UG'), ('BOA TZ', 'BOA TZ'), ('BOA RW', 'BOA RW'), ('BOA KE', 'BOA KE'), ('BOA FR', 'BOA FR'), ('BOA KM', 'BOA KM'), ('BOA GH', 'BOA GH'), ('BOA Group', 'BOA Group')], default='', max_length=15, null=True)),
                ('expl', models.CharField(blank=True, default='', max_length=50, null=True)),
                ('agence', models.CharField(blank=True, default='', max_length=50, null=True)),
                ('agence_lib', models.CharField(blank=True, default='', max_length=50, null=True)),
                ('nom', models.CharField(blank=True, default='', max_length=50, null=True)),
                ('email', models.CharField(blank=True, default='', max_length=200, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Anomalie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('FILIALE', models.CharField(blank=True, max_length=200)),
                ('AGENCE', models.CharField(blank=True, max_length=200)),
                ('LIB_AGENCE', models.CharField(blank=True, max_length=50)),
                ('EXPL', models.CharField(blank=True, max_length=200)),
                ('CLIENT', models.CharField(blank=True, max_length=200)),
                ('ANOMALIE_AGE', models.CharField(blank=True, max_length=200)),
                ('ANOMALIE_DATE_EER', models.CharField(blank=True, max_length=200)),
                ('ANOMALIE_CIN', models.CharField(blank=True, max_length=200)),
                ('PPE', models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='DATEREV',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('FILIALE', models.CharField(blank=True, max_length=10)),
                ('AGENCE', models.CharField(blank=True, max_length=10)),
                ('LIB_AGENCE', models.CharField(blank=True, max_length=50)),
                ('EXPL', models.CharField(blank=True, max_length=10)),
                ('CLIENT', models.CharField(blank=True, max_length=10)),
                ('DATEREV', models.DateField(blank=True, null=True)),
                ('PPE', models.CharField(blank=True, max_length=20)),
                ('RISQUE', models.CharField(blank=True, max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='Devise',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(choices=[('BOA NE', 'BOA NE'), ('BOA CI', 'BOA CI'), ('BOA TG', 'BOA TG'), ('BOA SN', 'BOA SN'), ('BOA ML', 'BOA ML'), ('BOA BF', 'BOA BF'), ('BOA BJ', 'BOA BJ'), ('BOA RDC', 'RDC'), ('LCB', 'LCB'), ('BCB', 'BCB'), ('BOA MR', 'BOA MR'), ('BOA MG', 'BOA MG'), ('BOA UG', 'BOA UG'), ('BOA TZ', 'BOA TZ'), ('BOA RW', 'BOA RW'), ('BOA KE', 'BOA KE'), ('BOA FR', 'BOA FR'), ('BOA KM', 'BOA KM'), ('BOA GH', 'BOA GH'), ('BOA Group', 'BOA Group')], default='', max_length=10)),
                ('devise', models.CharField(default='', max_length=4)),
            ],
        ),
        migrations.CreateModel(
            name='Kyc_pm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('FILIALE', models.CharField(blank=True, max_length=200)),
                ('AGENCE', models.CharField(blank=True, max_length=200)),
                ('LIB_AGENCE', models.CharField(blank=True, max_length=50)),
                ('EXPL', models.CharField(blank=True, max_length=200)),
                ('CLIENT', models.CharField(blank=True, max_length=200)),
                ('AGEC', models.CharField(blank=True, max_length=200)),
                ('CODAPE', models.CharField(blank=True, max_length=200)),
                ('IDM', models.CharField(blank=True, max_length=200)),
                ('RCSNO', models.CharField(blank=True, max_length=200)),
                ('CAPITAL', models.CharField(blank=True, max_length=200)),
                ('CA', models.CharField(blank=True, max_length=200)),
                ('RESULTAT', models.CharField(blank=True, max_length=200)),
                ('ORIGINE_REV', models.CharField(blank=True, max_length=200)),
                ('DATOUV', models.CharField(blank=True, max_length=200)),
                ('TEL', models.CharField(blank=True, max_length=200)),
                ('DEVISE', models.CharField(blank=True, max_length=200)),
                ('RESID', models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='Kyc_pp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('FILIALE', models.CharField(blank=True, max_length=200)),
                ('AGENCE', models.CharField(blank=True, max_length=200)),
                ('LIB_AGENCE', models.CharField(blank=True, max_length=50)),
                ('EXPL', models.CharField(blank=True, max_length=200)),
                ('CLIENT', models.CharField(blank=True, max_length=200)),
                ('CODAPE', models.CharField(blank=True, max_length=200)),
                ('IDP', models.CharField(blank=True, max_length=200)),
                ('PAYNAIS', models.CharField(blank=True, max_length=200)),
                ('PROFESSION', models.CharField(blank=True, max_length=200)),
                ('ADRESSE', models.CharField(blank=True, max_length=200)),
                ('PAYS_RESID', models.CharField(blank=True, max_length=200)),
                ('NUMID', models.CharField(blank=True, max_length=200)),
                ('SALAIRE', models.CharField(blank=True, max_length=200)),
                ('ORIGINE_REV', models.CharField(blank=True, max_length=200)),
                ('DATVALID', models.CharField(blank=True, max_length=200)),
                ('TEL', models.CharField(blank=True, max_length=200)),
                ('DATOUV', models.CharField(blank=True, max_length=200)),
                ('PPE', models.CharField(blank=True, max_length=200)),
                ('DEVISE', models.CharField(blank=True, max_length=200)),
                ('RESID', models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.EmailField(blank=True, default='', max_length=30)),
                ('first_name', models.CharField(blank=True, default='', max_length=30)),
                ('last_name', models.CharField(blank=True, default='', max_length=30)),
                ('email', models.EmailField(max_length=254)),
                ('telephone', models.CharField(blank=True, max_length=20)),
                ('password', models.CharField(blank=True, default='', max_length=32)),
                ('Photo_profil', models.ImageField(blank=True, null=True, upload_to='media')),
            ],
        ),
        migrations.CreateModel(
            name='TAUX_FILIALE',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('FILIALE', models.CharField(blank=True, max_length=10)),
                ('STOCK_PP', models.FloatField(blank=True, default='', max_length=10)),
                ('STOCK_PM', models.FloatField(blank=True, default='', max_length=10)),
                ('FLUX_PP', models.FloatField(blank=True, default='', max_length=10)),
                ('FLUX_PM', models.FloatField(blank=True, default='', max_length=10)),
            ],
        ),
        migrations.CreateModel(
            name='TauxEvolution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(blank=True, max_length=10)),
                ('agence', models.CharField(blank=True, max_length=50, null=True)),
                ('expl', models.CharField(blank=True, max_length=50)),
                ('date', models.DateField(blank=True)),
                ('taux', models.FloatField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('flux_stock', models.CharField(blank=True, max_length=50)),
                ('pp_pm', models.CharField(blank=True, max_length=50)),
            ],
            options={
                'ordering': ['filiale', 'expl', 'date'],
            },
        ),
        migrations.CreateModel(
            name='TauxEvolution_filiale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filiale', models.CharField(blank=True, max_length=10)),
                ('flux_PM', models.FloatField(blank=True, null=True)),
                ('flux_PP', models.FloatField(blank=True, null=True)),
                ('stock_PM', models.FloatField(blank=True, null=True)),
                ('stock_PP', models.FloatField(blank=True, null=True)),
                ('date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Compte',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_compte', models.CharField(blank=True, choices=[('PPE', 'Personne Politiquement Exposée'), ('DEV', 'Compte en Devise'), ('NON_RES', 'Non Résident'), ('scoring', 'Compte scoring')], max_length=10)),
                ('solde', models.DecimalField(decimal_places=2, max_digits=15)),
                ('devise', models.CharField(blank=True, max_length=3)),
                ('date_ouverture', models.DateField()),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kyc.agents')),
            ],
        ),
        migrations.CreateModel(
            name='Notation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note', models.CharField(choices=[('Très Bien', 'Très Bien'), ('Bien', 'Bien'), ('Passable', 'Passable'), ('Insuffisant', 'Insuffisant')], default='Bien', max_length=15)),
                ('flux_stock', models.CharField(choices=[('Flux', 'Flux'), ('Stock', 'Stock')], default='', max_length=15)),
                ('recommandation', models.TextField(blank=True, null=True)),
                ('date_notation', models.DateTimeField(default=django.utils.timezone.now)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kyc.agents')),
                ('note_par', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Historique',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kyc.agents')),
                ('notation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kyc.notation')),
            ],
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('avatar', models.ImageField(default='default.jpg', upload_to='profile_avatars/')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
