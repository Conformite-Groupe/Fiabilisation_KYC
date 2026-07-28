                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0054_remove_kycdocumentmatchsettings_birth_date_weight_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='dataqualitycondition',
            options={'ordering': ['id']},
        ),
        migrations.AddField(
            model_name='dataqualitycondition',
            name='logic',
            field=models.CharField(choices=[('AND', 'ET'), ('OR', 'OU')], default='AND', help_text='Connecteur logique avec la condition précédente (ET / OU). OU démarre un nouveau groupe ; ignoré pour la 1re condition.', max_length=3),
        ),
        migrations.AlterField(
            model_name='dataqualitycondition',
            name='operator',
            field=models.CharField(choices=[('=', 'Égal à (=)'), ('!=', 'Différent de (!=)'), ('>', 'Supérieur à (>)'), ('<', 'Inférieur à (<)'), ('>=', 'Supérieur ou égal (>=)'), ('<=', 'Inférieur ou égal (<=)'), ('contains', 'Contient'), ('not_contains', 'Ne contient pas'), ('contains_alpha', 'Contient des lettres'), ('contains_digit', 'Contient des chiffres'), ('regex', 'Expression régulière'), ('is_empty', 'Est vide'), ('is_not_empty', "N'est pas vide"), ('expired', "Est expiré (Date < Aujourd'hui)"), ('age_gt', 'Âge supérieur à'), ('age_lt', 'Âge inférieur à'), ('min_length', 'Longueur minimum'), ('max_length', 'Longueur maximum')], max_length=20),
        ),
    ]
