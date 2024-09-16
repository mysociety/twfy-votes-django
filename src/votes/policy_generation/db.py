"""
This module contains the sequence of macros to
generate a voting record for a person.
"""

from pathlib import Path

from django.conf import settings

from twfy_votes.helpers.duck import BaseQuery, DuckQuery, RawJinjaQuery

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")


@duck.as_table
class policy_divisions_relevant:
    source = compiled_dir / "policy_divisions_relevant.parquet"


@duck.as_table
class policy_agreements_relevant:
    source = compiled_dir / "policy_agreements_relevant.parquet"


@duck.as_table
class policy_votes_relevant:
    source = compiled_dir / "policy_votes_relevant.parquet"


@duck.as_query
class make_indexes:
    query = """
    CREATE INDEX division_id ON policy_divisions_relevant (id);
    CREATE INDEX votes_division ON policy_votes_relevant (division_id);
    CREATE INDEX votes_person ON policy_votes_relevant (person_id);
    """


@duck.as_table
class policy_collective_relevant:
    source = compiled_dir / "policy_collective_relevant.parquet"


@duck.as_alias
class pd_memberships_source:
    alias_for = "postgres_db.votes_membership"


@duck.as_source
class pw_relevant_people:
    source = compiled_dir / "relevant_person_policy_period.parquet"


@duck.as_table
class pd_memberships:
    query = """
    select * from pd_memberships_source
    where person_id in (select distinct person_id from pw_relevant_people)
    order by start_date
    """


@duck.as_alias
class policies:
    alias_for = "postgres_db.votes_policy"


@duck.as_table_macro
class target_memberships:
    """
    Table macro to get the memberships for a person in a chamber
    """

    args = ["_person_id", "_chamber_id"]
    macro = """
    select
        *
    from
        pd_memberships
    where
        person_id = {{ _person_id }} and
        chamber_id = {{ _chamber_id }}
    """


@duck.as_table_macro
class agreement_count:
    """
    We want to know, by person_id, how many agreements they were in parliament for by policy.
    By *definition* this is the same for both target and non_target, so can be merged in the last step.
    """

    args = ["_person_id"]
    macro = """
    select
        period_id,
        person_id,
        policy_id,
        -- count agreement where strength is strong and alignment is agree
        count(*) filter (where strong_int = 1 and agree_int = 1) as num_strong_agree_agreements,
        -- count agreement where strength is weak and alignment is agree
        count(*) filter (where strong_int = 0 and agree_int = 1) as num_weak_agree_agreements,
        -- count agreement where strength is strong and alignment is disagree
        count(*) filter (where strong_int = 1 and agree_int = 0) as num_strong_disagree_agreements,
        -- count agreement where strength is weak and alignment is disagree
        count(*) filter (where strong_int = 0 and agree_int = 0) as num_weak_disagree_agreements
    from
        policy_collective_relevant
    join
        policy_agreements_relevant
         on (policy_collective_relevant.decision_id = policy_agreements_relevant.id)
    where
        policy_collective_relevant.person_id = {{ _person_id }}
    group by
        all
    """


@duck.as_table_macro
class policy_alignment:
    """
    Table macro - For each vote/absence, calculate the policy alignment per person.
    """

    args = ["_person_id", "_chamber_id", "_party_id"]
    macro = """
    SELECT
        period_id,
        policy_id,
        pw_vote.person_id as person_id,
        case pw_vote.person_id when {{ _person_id }} then 1 else 0 end as is_target,
        strong_int,
        policy_divisions.id as division_id,
        policy_divisions.date as division_date,
        policy_divisions.division_number as division_number,
        policy_divisions.division_year as division_year,
        pw_vote.effective_vote as mp_vote,
        (case when pw_vote.effective_vote_int = 1 and agree_int = 1 
                or pw_vote.effective_vote_int = -1 and agree_int = 1 then 1 else 0 end) as answer_agreed,
        (case when pw_vote.effective_vote_int = 1 and agree_int = 0 
                or pw_vote.effective_vote_int = -1 and agree_int = 0 then 1 else 0 end) as answer_disagreed,
        pw_vote.abstain_int as abstained,
        pw_vote.absent_int as absent,
    FROM
        -- this is the divisions table merged with the division_links table and the period table
        policy_divisions_relevant as policy_divisions
    join
        -- limit to divisions within the memberships of our target person
        target_memberships({{ _person_id}}, {{ _chamber_id }}) as target_memberships
            on policy_divisions.date between target_memberships.start_date and target_memberships.end_date
    join
        -- now we bring in the actual votes
        -- this has already been reduced to only votes for divisions we care about
        policy_votes_relevant as pw_vote on (policy_divisions.id = pw_vote.division_id)
    where
        policy_divisions.chamber_id = {{ _chamber_id }}
        and ( -- here we want either the persons own divisions, or the divisions of the party they are in.
            pw_vote.person_id = {{ _person_id }}
            or
            pw_vote.effective_party_id = {{ _party_id }}
            )
    """


@duck.as_table_macro
class comparisons_by_policy_vote:
    """
    Table Macro.
    For each policy/vote, group up both the target and the comparison mps, and create an equiv score for the comparison
    This will be floats - but will sum to the same total of votes as the number of divisions the target could vote in.
    """

    args = ["_person_id", "_chamber_id", "_party_id"]
    macro = """
    select
        period_id,
        is_target,
        policy_id,
        division_id,
        ANY_VALUE(strong_int) as strong_int,
        count(*) as total,
        any_value(division_year) as division_year,
        sum(answer_agreed) / total as num_divisions_agreed,
        sum(answer_disagreed) / total as num_divisions_disagreed,
        sum(abstained) / total as num_divisions_abstained,
        sum(absent) / total as num_divisions_absent,
        sum(answer_agreed) + sum(answer_disagreed) + sum(abstained) + sum(absent) as num_comparators,
    from
        policy_alignment({{ _person_id }},
                         {{ _chamber_id }},
                         {{ _party_id }})
    group by
        period_id, is_target, policy_id, division_id
    """


@duck.as_table_macro
class comparisons_by_policy_vote_pivot:
    args = ["_person_id", "_chamber_id", "_party_slug"]
    macro = """
    select
        period_id,
        is_target,
        policy_id,
        sum(num_divisions_agreed) filter (where strong_int = 0) as num_votes_same,
        sum(num_divisions_agreed) filter (where strong_int = 1) as num_strong_votes_same,
        sum(num_divisions_disagreed) filter (where strong_int = 0) as num_votes_different,
        sum(num_divisions_disagreed) filter (where strong_int = 1) as num_strong_votes_different,
        sum(num_divisions_absent) filter (where strong_int = 0) as num_votes_absent,
        sum(num_divisions_absent) filter (where strong_int = 1) as num_strong_votes_absent,
        sum(num_divisions_abstained) filter (where strong_int = 0) as num_votes_abstained,
        sum(num_divisions_abstained) filter (where strong_int = 1) as num_strong_votes_abstained,
        list(num_comparators) as num_comparators,
        min(division_year) as start_year,
        max(division_year) as end_year
    from comparisons_by_policy_vote({{ _person_id }},
                                    {{ _chamber_id }},
                                    {{ _party_slug }}
                                    )
    group by
        period_id, is_target, policy_id
    """


@duck.as_table_macro
class joined_division_agreement_comparison:
    args = ["_person_id", "_chamber_id", "_party_slug"]
    macro = """
    select
        {{ _person_id }} as person_id,
        {{ _chamber_id }} as chamber,
        {{ _party_slug }} as party,
        division_comparison.*,
        agreement_comparison.*
    from
        comparisons_by_policy_vote_pivot({{ _person_id }},
                                        {{ _chamber_id }},
                                        {{ _party_slug }}
                                        ) as division_comparison
    left join
        agreement_count({{ _person_id }}) as agreement_comparison using (policy_id, period_id)
    """


@duck.as_query
class prepared_pivot_table:
    query = """
    PREPARE prepared_pivot_table AS
    select * from joined_division_agreement_comparison($person_id, $chamber_id, $party_id)
    """


class PolicyPivotTable(RawJinjaQuery):
    """
    Retrieve all policy breakdowns and comparison breakdowns
    for a single person, given a chamber and a party.
    """

    query_template = """
    EXECUTE prepared_pivot_table(person_id := {{ person_id }},
                                 chamber_id := {{ chamber_id }},
                                 party_id := {{ party_id }})
    """
    person_id: int
    chamber_id: int
    party_id: int


class GetPersonParties(BaseQuery):
    """
    Get all 'real' parties that a person has been a member of in a chamber.
    Excludes independents, etc.
    """

    query_template = """
    select * from (
    select distinct(party) as party from pd_memberships
    where chamber == {{ chamber_id }}
    and person_id == {{ person_id }}
    )
    {% if banned_parties %}
    where party not in {{ banned_parties | inclause }}
    {% endif %}
    """
    chamber_id: str
    person_id: int
    banned_parties: list[str] = [
        "independent",
        "speaker",
        "deputy-speaker",
        "independent-conservative",
        "independent-labour",
        "independent-ulster-unionist",
    ]


class PolicyDistributionQuery(BaseQuery):
    """
    Here we're joining with the comparison party table to limit to just the
    'official' single comparisons used in TWFY.

    Here in this app, we can store and display multiple comparisons.
    """

    query_template = """
    select
        policy_distributions.*,
        policies.strength_meaning as strength_meaning
    from 
        policy_distributions
    join
        policies on (policy_distributions.policy_id = policies.id)
    {% if single_comparisons %}
    join
        pw_comparison_party using (person_id, chamber, comparison_party)
    {% endif %}
    where
        policy_id = {{ policy_id }}
        and period_id = {{ period_id }}
    """
    policy_id: int
    period_id: str
    single_comparisons: bool = False


def get_connected_duck():
    connected = DuckQuery.connect()
    connected.compile(duck).run()
    return connected