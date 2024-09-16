"""
Store the duckdb connectors to share between functions
"""

from pathlib import Path

from django.conf import settings

from twfy_votes.helpers.duck import DuckQuery

from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")


@duck.as_alias
class pw_division:
    alias_for = "postgres_db.votes_division"


@duck.as_alias
class pw_agreement:
    alias_for = "postgres_db.votes_agreement"


@duck.as_alias
class pd_memberships:
    alias_for = "postgres_db.votes_membership"


@duck.as_alias
class pd_org:
    alias_for = "postgres_db.votes_organization"


@duck.as_alias
class policy_votes:
    alias_for = "postgres_db.votes_policydivisionlink"


@duck.as_alias
class policy_agreements:
    alias_for = "postgres_db.votes_policyagreementlink"


@duck.as_alias
class policy_comparison_period:
    alias_for = "postgres_db.votes_policycomparisonperiod"


@duck.as_source
class pw_vote:
    source = compiled_dir / "votes_with_parties.parquet"


@duck.to_parquet(
    dest=compiled_dir / "policy_divisions_relevant.parquet", reuse_as_source=True
)
class policy_divisions_relevant:
    """
    Expand the policy_votes tables with links to division_ids, and to time periods

    """

    query = """
    select 
        pw_division.*,
        date_part('year',date) as division_year,
        case when policy_votes.strength = 'strong' then 1 else 0 end as strong_int,
        case when policy_votes.alignment = 'agree' then 1 else 0 end as agree_int,
        strong_int * 2 + agree_int as combo_int,
        policy_votes.* exclude (decision_id, id),
        policy_comparison_period.slug as period_slug,
        policy_comparison_period.id as period_id
    from 
        policy_votes
    left join
        pw_division on (policy_votes.decision_id = pw_division.id)
    left join 
        policy_comparison_period on (
            pw_division.date between policy_comparison_period.start_date and policy_comparison_period.end_date)
    order by 
        pw_division.id, policy_id, period_id
    """


@duck.to_parquet(compiled_dir / "policy_votes_relevant.parquet", reuse_as_source=True)
class votes_relevant:
    """
    Limit the votes table to just those where the division is part of policy_votes
    """

    query = """
    select 
        pw_vote.* exclude (division_id),
        pd_org.id as effective_party_id,
        -- if effective_vote is aye then 1, no then -1, otherwise 0
        case when effective_vote = 'aye' then 1 when effective_vote = 'no' then -1 else 0 end as effective_vote_int,
        -- when effective_vote is absent, then absent is 1
        case when effective_vote = 'absent' then 1 else 0 end as absent_int, 
        case when effective_vote = 'abstain' then 1 else 0 end as abstain_int,
        pw_division.id as division_id,
        pw_division.key as division_key
    from 
        pw_vote
    join
        pw_division on (pw_vote.division_id = pw_division.key)
    join
        pd_org on (pw_vote.effective_party_slug = pd_org.slug)
    where
        pw_division.id in (select distinct decision_id from policy_votes)
    order by
        person_id, division_id
    """


@duck.to_parquet(
    dest=compiled_dir / "policy_agreements_relevant.parquet", reuse_as_source=True
)
class policy_agreements_relevant:
    """
    Expand the policy_agreements tables with links to division_ids, and to time periods
    """

    query = """
    select 
        pw_agreement.*,
        case when policy_agreements.strength = 'strong' then 1 else 0 end as strong_int,
        case when policy_agreements.alignment = 'agree' then 1 else 0 end as agree_int,
        strong_int * 2 + agree_int as combo_int,
        policy_agreements.* exclude (decision_id, id),
        policy_comparison_period.slug as period_slug,
        policy_comparison_period.id as period_id
    from 
        policy_agreements
    left join
        pw_agreement on (policy_agreements.decision_id = pw_agreement.id)
    left join 
        policy_comparison_period on (
            pw_agreement.date between policy_comparison_period.start_date and policy_comparison_period.end_date)
    order by
        pw_agreement.id, policy_id, period_id
    """


@duck.to_parquet(
    dest=compiled_dir / "policy_collective_relevant.parquet", reuse_as_source=True
)
class collective_relevant:
    """
    Calculate the people are are 'present' in Parliament when an agreement is reached
    """

    query = """
    select
        pd_memberships.id as membership_id,
        pd_memberships.person_id as person_id,
        pw_agreement.*,
        policy_agreements.decision_id as decision_id,
        'collective' as effective_vote
    from
        pw_agreement
    join
        policy_agreements on (pw_agreement.id = policy_agreements.decision_id)
    join
        pd_memberships on (pw_agreement.date between pd_memberships.start_date and pd_memberships.end_date
        and pd_memberships.chamber_id = pw_agreement.chamber_id)
        
    order by
        person_id, pw_agreement.date, decision_id
    """


@duck.as_view
class relevant_parties_for_people:
    query = """
        select
            person_id,
            effective_party_slug,
            effective_party_id as party_id,
            chamber_id
        from
            pd_memberships
        where
            effective_party_slug not in (
                                            'independent', 'speaker', 'deputy-speaker', 'independent-conservative',
                                            'independent-labour', 'independent-ulster-unionist'
                                        )
            and party_id is not null
    """


@duck.as_view
class relevant_people_divisions:
    """
    We want to log at this point the people who have a connection to a specific policy
    in a specific time period
    """

    query = """
    select
        policy_divisions_relevant.chamber_id as chamber_id,
        policy_divisions_relevant.policy_id as policy_id,
        votes_relevant.person_id as person_id,
        policy_divisions_relevant.period_id
    from votes_relevant
    join
        policy_divisions_relevant on (votes_relevant.division_id = policy_divisions_relevant.id)
    """


@duck.as_view
class relevant_people_agreements:
    """
    We want to log at this point the people who have a connection to a specific policy
    in a specific time period
    """

    query = """
    select
        policy_agreements_relevant.chamber_id as chamber_id,
        policy_agreements_relevant.policy_id as policy_id,
        collective_relevant.person_id as person_id,
        policy_agreements_relevant.period_id
    from collective_relevant
    join
        policy_agreements_relevant on (collective_relevant.decision_id = policy_agreements_relevant.id)
    """


@duck.to_parquet(
    compiled_dir / "relevant_person_policy_period.parquet", reuse_as_source=True
)
class relevant_people:
    """
    This contains a mapping for every single policy relationship we should end up with
    person_id, policy_id, period_id, chamber_id, party_id
    """

    query = """
    select distinct 
    * 
    from
    (select * from relevant_people_divisions
    union
    select * from relevant_people_agreements)
    left join
        relevant_parties_for_people using (person_id, chamber_id)
    """


@import_register.register("prep_policycalc", group=ImportOrder.PREP_POLICYCALC)
def run_pre_calc(quiet: bool = False):
    with DuckQuery.connect() as cduck:
        cduck.compile(duck).run()
