from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")

votes_with_parties = compiled_dir / "votes_with_parties.parquet"
division_with_counts = compiled_dir / "division_with_counts.parquet"
divisions_party_with_counts = compiled_dir / "divisions_party_with_counts.parquet"
divisions_gov_with_counts = compiled_dir / "divisions_gov_with_counts.parquet"


duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_source
class cm_votes_with_people:
    source = votes_with_parties


@duck.to_parquet(dest=division_with_counts)
class pw_divisions_with_counts:
    """
    Get the counts for and against in a division
    """

    query = """
    select
        division_id,
        count(*) as vote_participant_count,
        any_value(total_possible_members) as total_possible_members,
        sum(case when effective_vote = 'aye' then 1 else 0 end) as for_motion,
        sum(case when effective_vote = 'no' then 1 else 0 end) as against_motion,
        sum(case when effective_vote = 'both' then 1 else 0 end) as neutral_motion,
        for_motion + against_motion as signed_votes,
        for_motion - against_motion as motion_majority,
        for_motion / signed_votes as for_motion_percentage,
        case 
            when motion_majority = 0 then 0
            when motion_majority > 0 then 1
            when motion_majority < 0 then -1
        end as motion_result_int

        from
        cm_votes_with_people
        group by
            all
    """


@duck.to_parquet(dest=divisions_party_with_counts)
class pw_divisions_party_with_counts:
    """
    Get the counts for and against in a division (within a party)
    """

    query = """
    SELECT
        division_id,
        effective_party_slug as grouping,
        count(*) as vote_participant_count,
        any_value(total_possible_members) as total_possible_members,
        sum(case when effective_vote = 'aye' then 1 else 0 end) as for_motion,
        sum(case when effective_vote = 'no' then 1 else 0 end) as against_motion,
        sum(case when effective_vote = 'abstention' then 1 else 0 end) as neutral_motion,
        for_motion + against_motion as signed_votes,
        for_motion - against_motion as motion_majority,
        for_motion / signed_votes as for_motion_percentage,
        case 
            when motion_majority = 0 then 0
            when motion_majority > 0 then 1
            when motion_majority < 0 then -1
        end as motion_result_int
    FROM
        cm_votes_with_people
    GROUP BY 
        all
    """


@duck.to_parquet(dest=divisions_gov_with_counts)
class pw_divisions_gov_with_counts:
    """
    Get the counts for and against in a division (by government and 'other' reps)
    """

    query = """
    SELECT
        division_id,
        is_gov as grouping,
        count(*) as vote_participant_count,
        any_value(total_possible_members) as total_possible_members,
        sum(case when effective_vote = 'aye' then 1 else 0 end) as for_motion,
        sum(case when effective_vote = 'no' then 1 else 0 end) as against_motion,
        sum(case when effective_vote = 'both' then 1 else 0 end) as neutral_motion,
        for_motion + against_motion as signed_votes,
        for_motion - against_motion as motion_majority,
        for_motion / signed_votes as for_motion_percentage,
        case 
            when motion_majority = 0 then 0
            when motion_majority > 0 then 1
            when motion_majority < 0 then -1
        end as motion_result_int
    FROM
        cm_votes_with_people
    GROUP BY
        all
    """


@import_register.register("breakdowns", group=ImportOrder.BREAKDOWNS)
def import_votes(quiet: bool = False):
    # better on memory to write straight out as parquet, close duckdb and read in the parquet
    with DuckQuery.connect() as query:
        query.compile(duck).run()

    for path, unique_columns in [
        (division_with_counts, ("division_id",)),
        (divisions_party_with_counts, ("division_id", "grouping")),
        (divisions_gov_with_counts, ("division_id", "grouping")),
    ]:
        df = pd.read_parquet(path)
        # check unique
        if df.duplicated(subset=unique_columns).any():
            raise ValueError(f"Duplicate rows in {path}")
        if not quiet:
            rich.print(
                f"Created {path}, with [green]{len(df)}[/green] rows, duplicate check [green]passed[/green]"
            )
