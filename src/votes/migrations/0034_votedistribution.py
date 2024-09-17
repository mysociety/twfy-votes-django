# Generated by Django 4.2.15 on 2024-09-16 20:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("votes", "0033_membership_effective_party"),
    ]

    operations = [
        migrations.CreateModel(
            name="VoteDistribution",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        default=None, primary_key=True, serialize=False
                    ),
                ),
                ("is_target", models.IntegerField()),
                ("num_votes_same", models.FloatField()),
                ("num_strong_votes_same", models.FloatField()),
                ("num_votes_different", models.FloatField()),
                ("num_strong_votes_different", models.FloatField()),
                ("num_votes_absent", models.FloatField()),
                ("num_strong_votes_absent", models.FloatField()),
                ("num_votes_abstain", models.FloatField()),
                ("num_strong_votes_abstain", models.FloatField()),
                ("num_agreements_same", models.FloatField()),
                ("num_strong_agreements_same", models.FloatField()),
                ("num_agreements_different", models.FloatField()),
                ("num_strong_agreements_different", models.FloatField()),
                ("start_year", models.IntegerField()),
                ("end_year", models.IntegerField()),
                ("distance_score", models.FloatField()),
                (
                    "chamber",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="vote_distributions",
                        to="votes.chamber",
                    ),
                ),
                (
                    "comparison",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="vote_distributions",
                        to="votes.policycomparisonperiod",
                    ),
                ),
                (
                    "party",
                    models.ForeignKey(
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="vote_distributions",
                        to="votes.organization",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="vote_distributions",
                        to="votes.person",
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="vote_distributions",
                        to="votes.policy",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
