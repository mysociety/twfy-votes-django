# Generated by Django 4.2.15 on 2025-04-12 19:27

from django.db import migrations, models


def update_tag_type(apps, schema_editor):
    DecisionTag = apps.get_model("votes", "DecisionTag")
    DecisionTag.objects.filter(tag_type="parl_bill").update(tag_type="legislation")


class Migration(migrations.Migration):

    dependencies = [
        ("votes", "0018_alter_agreement_tags_alter_division_tags_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="decisiontag",
            name="extra_data",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="decisiontag",
            name="tag_type",
            field=models.CharField(
                choices=[
                    ("gov_clusters", "Gov Clusters"),
                    ("misc", "Misc"),
                    ("legislation", "Legislation"),
                ],
                max_length=255,
            ),
        ),
        migrations.RunPython(update_tag_type),
    ]
