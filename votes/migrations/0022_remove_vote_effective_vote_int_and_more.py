# Generated by Django 4.2.15 on 2024-09-02 16:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0021_remove_division_absent_total_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='vote',
            name='effective_vote_int',
        ),
        migrations.AddField(
            model_name='vote',
            name='effective_vote_float',
            field=models.FloatField(default=0.0),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='vote',
            name='effective_vote',
            field=models.CharField(choices=[('aye', 'Aye'), ('no', 'No'), ('abstain', 'Abstain'), ('absent', 'Absent'), ('tellno', 'Tellno'), ('tellaye', 'Tellaye'), ('collective', 'Collective')], max_length=255),
        ),
        migrations.AlterField(
            model_name='vote',
            name='vote',
            field=models.CharField(choices=[('aye', 'Aye'), ('no', 'No'), ('abstain', 'Abstain'), ('absent', 'Absent'), ('tellno', 'Tellno'), ('tellaye', 'Tellaye'), ('collective', 'Collective')], max_length=255),
        ),
    ]
