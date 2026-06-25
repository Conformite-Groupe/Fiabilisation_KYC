from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0019_add_kyc_extra_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataqualityrule',
            name='filiale',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
