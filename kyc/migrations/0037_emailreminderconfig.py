from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0036_filialemoduleconfig'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailReminderConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('smtp_host', models.CharField(default='smtp.gmail.com', max_length=200, verbose_name='Serveur SMTP')),
                ('smtp_port', models.IntegerField(default=587, verbose_name='Port SMTP')),
                ('smtp_user', models.EmailField(verbose_name='Utilisateur SMTP')),
                ('smtp_password', models.CharField(max_length=300, verbose_name='Mot de passe SMTP')),
                ('smtp_use_tls', models.BooleanField(default=True, verbose_name='Utiliser TLS')),
                ('smtp_use_ssl', models.BooleanField(default=False, verbose_name='Utiliser SSL')),
                ('from_email', models.EmailField(verbose_name='Email expéditeur')),
                ('from_name', models.CharField(default='KYC Portal BOA', max_length=100, verbose_name='Nom expéditeur')),
                ('frequency', models.CharField(
                    choices=[('manual', 'Manuel uniquement'), ('daily', 'Quotidien'),
                              ('weekly', 'Hebdomadaire'), ('monthly', 'Mensuel')],
                    default='manual', max_length=20, verbose_name='Fréquence')),
                ('days_before', models.IntegerField(
                    default=30,
                    help_text='Inclure les clients dont la DATEREV expire dans ce nombre de jours',
                    verbose_name='Jours avant expiration')),
                ('active', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuration Rappel DATEREV',
                'verbose_name_plural': 'Configurations Rappel DATEREV',
            },
        ),
    ]
