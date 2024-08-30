# Generated by Django 4.2.15 on 2024-08-30 20:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0013_rename_partial_hash_policy_policy_hash'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agreement',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='chamber',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='division',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='governmentparty',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='policy',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='policyagreementlink',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='policydivisionlink',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='policygroup',
            name='id',
            field=models.BigAutoField(default=None, primary_key=True, serialize=False),
        ),
    ]
