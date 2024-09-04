# Generated by Django 4.2.15 on 2024-09-02 13:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0019_rename_organization_membership_chamber_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='governmentparty',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], default='', max_length=255),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='agreement',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], max_length=255),
        ),
        migrations.AlterField(
            model_name='chamber',
            name='slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], max_length=255),
        ),
        migrations.AlterField(
            model_name='division',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], max_length=255),
        ),
        migrations.AlterField(
            model_name='orgmembershipcount',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], max_length=255),
        ),
        migrations.AlterField(
            model_name='policy',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni')], max_length=255),
        ),
    ]