# Generated by Django 4.2.15 on 2024-09-04 19:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0026_alter_vote_effective_vote_float'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vote',
            name='diff_from_party_average',
            field=models.FloatField(null=True),
        ),
    ]
