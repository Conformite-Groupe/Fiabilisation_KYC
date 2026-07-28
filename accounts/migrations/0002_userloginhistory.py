                                               

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserLoginHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('login_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Historique de connexion',
                'verbose_name_plural': 'Historiques de connexion',
                'ordering': ('-login_at',),
                'indexes': [models.Index(fields=['login_at', 'user'], name='accounts_us_login_a_61a31a_idx')],
            },
        ),
    ]
