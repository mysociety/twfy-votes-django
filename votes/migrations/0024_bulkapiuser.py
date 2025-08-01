# Generated by Django 4.2.15 on 2025-06-26 11:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0023_alter_motion_motion_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='BulkAPIUser',
            fields=[
                ('id', models.BigAutoField(default=None, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=255)),
                ('token', models.CharField(default='', max_length=255)),
                ('purpose', models.TextField(default='')),
                ('enabled', models.BooleanField(default=True)),
                ('access_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField()),
                ('last_accessed', models.DateTimeField(blank=True, default=None, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
