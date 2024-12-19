# Generated by Django 4.2.15 on 2024-12-19 19:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('votes', '0009_analysisoverride'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPersonLink',
            fields=[
                ('id', models.BigAutoField(default=None, primary_key=True, serialize=False)),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='user_person_links', to='votes.person')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='user_person_links', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
