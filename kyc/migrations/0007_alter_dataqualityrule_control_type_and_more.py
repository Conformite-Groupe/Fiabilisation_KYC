                                                

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kyc', '0006_alter_dataqualityrule_options_kyc_pp_datnais_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataqualityrule',
            name='control_type',
            field=models.CharField(choices=[('simple', 'Contrôle simple (Existence / Valeur)'), ('composite', 'Règle multi-critères (Composite)')], max_length=50),
        ),
        migrations.CreateModel(
            name='DataQualityRuleAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rule_name', models.CharField(max_length=200)),
                ('action', models.CharField(max_length=50)),
                ('details', models.TextField(blank=True, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
    ]
