# Generated by Django 4.2.15 on 2024-09-04 16:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0023_alter_policyagreementlink_decision_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='membership',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], default='', max_length=255),
            preserve_default=False,
        ),
    ]