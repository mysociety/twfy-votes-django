# Generated by Django 4.2.15 on 2025-03-19 12:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0014_alter_agreement_chamber_alter_agreement_motion_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='divisionbreakdown',
            name='teller_against_motion',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='divisionbreakdown',
            name='teller_for_motion',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='divisionpartybreakdown',
            name='teller_against_motion',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='divisionpartybreakdown',
            name='teller_for_motion',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='divisionsisgovbreakdown',
            name='teller_against_motion',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='divisionsisgovbreakdown',
            name='teller_for_motion',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
    ]
