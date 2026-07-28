                                                

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_profilev_filiale_alter_zone_filiale'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('username', models.CharField(blank=True, default='', help_text='Identifiant saisi (conserve meme si le compte est supprime).', max_length=150)),
                ('filiale', models.CharField(blank=True, default='', max_length=20)),
                ('organe', models.CharField(blank=True, default='', max_length=50)),
                ('category', models.CharField(choices=[('CONNEXION', 'Connexion'), ('HABILITATION', 'Habilitation'), ('IMPORT', 'Import de donnees'), ('DONNEES', 'Mise a jour de donnees'), ('CONFIG', 'Parametrage'), ('EXPORT', 'Export'), ('SCREENING', 'Screening KYC ID'), ('SECURITE', 'Securite')], db_index=True, default='DONNEES', max_length=20)),
                ('action', models.CharField(default='', max_length=120)),
                ('target', models.CharField(blank=True, default='', help_text='Objet concerne (utilisateur, regle, lot, fichier...).', max_length=255)),
                ('details', models.TextField(blank=True, default='')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, default='', max_length=255)),
                ('success', models.BooleanField(default=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': "Evenement d'audit",
                'verbose_name_plural': "Evenements d'audit",
                'ordering': ('-timestamp',),
                'indexes': [models.Index(fields=['timestamp', 'category'], name='accounts_au_timesta_d14323_idx'), models.Index(fields=['user', 'timestamp'], name='accounts_au_user_id_a8a643_idx')],
            },
        ),
    ]
