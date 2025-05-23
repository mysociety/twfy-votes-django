# Generated by Django 4.2.15 on 2024-11-25 14:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('votes', '0002_remove_agreement_voting_cluster_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Motion',
            fields=[
                ('id', models.BigAutoField(default=None, primary_key=True, serialize=False)),
                ('gid', models.CharField(max_length=255)),
                ('speech_id', models.CharField(max_length=255)),
                ('date', models.DateField()),
                ('title', models.CharField(max_length=255)),
                ('text', models.TextField()),
                ('motion_type', models.CharField(choices=[('amendment', 'Amendment'), ('ten_minute_rule', 'Ten Minute Rule'), ('lords_amendment', 'Lords Amendment'), ('first_stage', 'First Stage'), ('second_stage', 'Second Stage'), ('committee_clause', 'Committee Clause'), ('second_stage_committee', 'Second Stage Committee'), ('third_stage', 'Third Stage'), ('approve_statutory_instrument', 'Approve Statutory Instrument'), ('revoke_statutory_instrument', 'Revoke Statutory Instrument'), ('adjournment', 'Adjournment'), ('timetable_change', 'Timetable Change'), ('humble_address', 'Humble Address'), ('government_agenda', 'Government Agenda'), ('financial', 'Financial'), ('confidence', 'Confidence'), ('standing_order_change', 'Standing Order Change'), ('private_sitting', 'Private Sitting'), ('eu_document_scrutiny', 'Eu Document Scrutiny'), ('other', 'Other'), ('proposed_clause', 'Proposed Clause'), ('bill_introduction', 'Bill Introduction'), ('unknown', 'Unknown'), ('reasoned_amendment', 'Reasoned Amendment')], max_length=255)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='agreement',
            name='motion',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='agreements', to='votes.motion'),
        ),
        migrations.AddField(
            model_name='division',
            name='motion',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='divisions', to='votes.motion'),
        ),
    ]
