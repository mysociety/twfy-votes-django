# Generated by Django 4.2.15 on 2024-09-02 11:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0018_division_total_possible_members'),
    ]

    operations = [
        migrations.RenameField(
            model_name='membership',
            old_name='organization',
            new_name='chamber',
        ),
        migrations.RenameField(
            model_name='membership',
            old_name='on_behalf_of',
            new_name='party',
        ),
    ]
