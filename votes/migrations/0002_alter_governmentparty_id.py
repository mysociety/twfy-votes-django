# Generated by Django 4.2.15 on 2024-08-29 15:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='governmentparty',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
    ]
