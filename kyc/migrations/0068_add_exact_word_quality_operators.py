from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0067_alter_devise_filiale_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataqualitycondition',
            name='operator',
            field=models.CharField(
                choices=[
                    ('=', 'Égal à (=)'),
                    ('!=', 'Différent de (!=)'),
                    ('>', 'Supérieur à (>)'),
                    ('<', 'Inférieur à (<)'),
                    ('>=', 'Supérieur ou égal (>=)'),
                    ('<=', 'Inférieur ou égal (<=)'),
                    ('contains', 'Contient'),
                    ('not_contains', 'Ne contient pas'),
                    ('word_contains', 'Contient le mot exact'),
                    ('word_not_contains', 'Ne contient pas le mot exact'),
                    ('contains_alpha', 'Contient des lettres'),
                    ('contains_digit', 'Contient des chiffres'),
                    ('regex', 'Expression régulière'),
                    ('is_empty', 'Est vide'),
                    ('is_not_empty', "N'est pas vide"),
                    ('expired', "Est expiré (Date < Aujourd'hui)"),
                    ('age_gt', 'Âge supérieur à'),
                    ('age_lt', 'Âge inférieur à'),
                    ('min_length', 'Longueur minimum'),
                    ('max_length', 'Longueur maximum'),
                ],
                max_length=20,
            ),
        ),
    ]
