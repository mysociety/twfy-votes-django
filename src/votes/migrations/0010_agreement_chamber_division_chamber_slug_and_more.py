# Generated by Django 4.2.15 on 2024-08-30 15:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0009_alter_governmentparty_chamber'),
    ]

    operations = [
        migrations.AddField(
            model_name='agreement',
            name='chamber',
            field=models.ForeignKey(default='', on_delete=django.db.models.deletion.DO_NOTHING, related_name='agreements', to='votes.chamber'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='division',
            name='chamber_slug',
            field=models.CharField(choices=[('commons', 'Commons'), ('lords', 'Lords'), ('scotland', 'Scotland'), ('senedd', 'Senedd'), ('ni', 'Ni'), ('pbc', 'Pbc')], default='', max_length=255),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='agreement',
            name='decision_name',
            field=models.CharField(max_length=255),
        ),
    ]