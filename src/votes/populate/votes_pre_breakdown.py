from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
votes_with_absences = Path(BASE_DIR, "data", "compiled", "votes_with_absences.parquet")
votes_with_parties = Path(BASE_DIR, "data", "compiled", "votes_with_parties.parquet")

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_source
class pw_vote:
    source = Path(BASE_DIR, "data", "source", "votes.parquet")


@duck.as_macro
class reduce_votes:
    """
    Reduce a list of votes to a single value.
    Prefer 'tellno' to 'no' and 'tellaye' to 'aye'.
    """

    args = ["votes"]
    macro = """
        case
            when array_contains(list(votes), 'tellno') then 'tellno'
            when array_contains(list(votes), 'tellaye') then 'tellaye'
            when array_contains(list(votes), 'both') then 'abstain'
            when array_contains(list(votes), 'no') then 'no'
            when array_contains(list(votes), 'aye') then 'aye'
            else last(votes)
        end
    """


@duck.as_view
class pw_vote_deduped:
    """
    Remove duplicate votes under different memberships for the same person - preferring the later membership.

    So the problem here is we *are* removing duplicate votes, but sometimes there is a duplicate tellno no.
    """

    query = """
    SELECT
        division_id,
        person_id,
        reduce_votes(vote) as vote,
        last(membership_id) as membership_id
    FROM
        (select *
            from pw_vote
        where vote != 'absent' and division_id not like '%cy-senedd'
        order by membership_id)
    GROUP BY
        division_id,
        person_id
    """


@duck.as_macro
class get_effective_vote:
    """
    Reduce values so tellers are counted as aye or no
    """

    args = ["vote"]
    macro = """
    case vote
        when 'tellaye' then 'aye'
        when 'tellno' then 'no'
        else vote
    end       
    """


@duck.as_macro
class get_clean_vote:
    """
    Remove 'both' entries from the vote column.
    Conform on 'abstention' as the value for 'both'
    """

    args = ["vote"]
    macro = """
        case
            when vote = 'both' then 'abstention'
            else vote
        end
    """


@duck.as_macro
class get_effective_party:
    """
    Reduce variant parties to a single canonical entry
    mostly taking out the co-operative part of labour/co-operative
    """

    args = ["party"]
    macro = """
        case
            when party = 'labourco-operative' then 'labour'
            else party
        end
    """


@duck.as_alias
class pw_division:
    alias_for = "postgres_db.votes_division"


@duck.as_alias
class pd_people:
    alias_for = "postgres_db.votes_person"


@duck.as_alias
class pd_membership:
    alias_for = "postgres_db.votes_membership"


@duck.as_alias
class government_parties_basic:
    alias_for = "postgres_db.votes_governmentparty"


@duck.as_view
class government_parties:
    query = """
        select
            *,
            True as is_gov
        from
        government_parties_basic
    """


@duck.to_parquet(dest=votes_with_absences)
class pw_vote_with_absences:
    """
    Creates an 'absent' vote record for each mp for each division they were absent for.
    """

    query = """
    select
        pw_division.key as division_id,
        pdm.id as membership_id,
        pdm.person_id as person_id,
        case when vote is null then 'absent' else vote end as vote
    from
        pw_division
    join
        pd_membership as pdm on
            (pw_division.date between pdm.start_date
             and pdm.end_date
             and pw_division.chamber_slug = pdm.chamber_slug)
    left join
        pw_vote_deduped as pw_vote on (pw_vote.division_id = pw_division.key and pw_vote.membership_id = pdm.id)
    """


@duck.as_source
class calc_vote_with_absences:
    source = votes_with_absences


@duck.to_parquet(dest=votes_with_parties)
class calculate_votes:
    """
    Use political data to get more information into the votes table
    """

    query = """
    SELECT
        pw_vote.* EXCLUDE (person_id),
        get_effective_vote(vote) as effective_vote,
        pw_vote.person_id as person_id,
        pd_membership.effective_party_slug as effective_party_slug,
        CASE WHEN government_parties.is_gov is NULL THEN 0 ELSE 1 END AS is_gov,
        total_possible_members
    FROM
        calc_vote_with_absences as pw_vote
    JOIN
        pd_membership on (pw_vote.membership_id = pd_membership.id)
    JOIN
        pd_people on (pw_vote.person_id = pd_people.id)
    LEFT JOIN
        pw_division on (pw_vote.division_id = pw_division.key)
    LEFT JOIN government_parties 
        government_parties on
            (date between government_parties.start_date and 
            government_parties.end_date and 
            government_parties.party = pd_membership.effective_party_slug and
            pw_division.chamber_id = government_parties.chamber_id)
    WHERE
        pw_division.chamber_slug != 'pbc'
    """


@import_register.register("votes_pre_breakdown", group=ImportOrder.PRE_BREAKDOWNS)
def import_votes(quiet: bool = False):
    # better on memory to write straight out as parquet, close duckdb and read in the parquet
    with DuckQuery.connect() as query:
        query.compile(duck).run()

    df = pd.read_parquet(votes_with_parties)

    df["key"] = df["division_id"].astype(str) + "-" + df["person_id"].astype(str)

    all_keys = df["key"].unique()

    # check for duplicates
    if len(all_keys) != len(df):
        raise ValueError("Duplicate keys found in the votes table")

    if not quiet:
        rich.print(
            f"Calculated votes table has [green]{len(df)}[/green] rows, duplicate check [green]passed[/green]"
        )
