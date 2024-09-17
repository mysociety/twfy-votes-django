import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..models.decisions import (
    Division,
    DivisionBreakdown,
    DivisionPartyBreakdown,
    DivisionsIsGovBreakdown,
)
from ..models.people import (
    Organization,
)
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
        sum(case when effective_vote = 'abstain' then 1 else 0 end) as neutral_motion,
        sum(case when effective_vote = 'absent' then 1 else 0 end) as absent_motion,
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
        sum(case when effective_vote = 'abstain' then 1 else 0 end) as neutral_motion,
        sum(case when effective_vote = 'absent' then 1 else 0 end) as absent_motion,
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
        sum(case when effective_vote = 'abstain' then 1 else 0 end) as neutral_motion,
        sum(case when effective_vote = 'absent' then 1 else 0 end) as absent_motion,
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
def import_breakdowns(quiet: bool = False, update_since: datetime.date | None = None):
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

    if update_since:
        affected_divisions_ids = list(
            Division.objects.filter(date__gte=update_since).values_list("id", flat=True)
        )
    else:
        affected_divisions_ids = None
    # load into database
    division_key_to_id = Division.id_from_slug("key")
    df = pd.read_parquet(division_with_counts)
    to_create = []
    for _, row in df.iterrows():
        # only create for new divisions
        if (
            affected_divisions_ids
            and division_key_to_id[row["division_id"]] not in affected_divisions_ids
        ):
            continue
        to_create.append(
            DivisionBreakdown(
                division_id=division_key_to_id[row["division_id"]],
                vote_participant_count=row["vote_participant_count"],
                total_possible_members=row["total_possible_members"],
                for_motion=row["for_motion"],
                against_motion=row["against_motion"],
                neutral_motion=row["neutral_motion"],
                absent_motion=row["absent_motion"],
                signed_votes=row["signed_votes"],
                motion_majority=row["motion_majority"],
                for_motion_percentage=row["for_motion_percentage"],
                motion_result_int=row["motion_result_int"],
            )
        )

    with DivisionBreakdown.disable_constraints():
        if affected_divisions_ids:
            DivisionBreakdown.objects.filter(
                division_id__in=affected_divisions_ids
            ).delete()
        else:
            DivisionBreakdown.objects.all().delete()
        DivisionBreakdown.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] division breakdowns")

    to_create = []

    df = pd.read_parquet(divisions_party_with_counts)

    org_id_lookup = Organization.id_from_slug("slug")

    for _, row in df.iterrows():
        # only create for new divisions
        if (
            affected_divisions_ids
            and division_key_to_id[row["division_id"]] not in affected_divisions_ids
        ):
            continue
        to_create.append(
            DivisionPartyBreakdown(
                division_id=division_key_to_id[row["division_id"]],
                party_slug=row["grouping"],
                party_id=org_id_lookup[row["grouping"]],
                vote_participant_count=row["vote_participant_count"],
                total_possible_members=row["total_possible_members"],
                for_motion=row["for_motion"],
                against_motion=row["against_motion"],
                neutral_motion=row["neutral_motion"],
                absent_motion=row["absent_motion"],
                signed_votes=row["signed_votes"],
                motion_majority=row["motion_majority"],
                for_motion_percentage=row["for_motion_percentage"],
                motion_result_int=row["motion_result_int"],
            )
        )

    with DivisionPartyBreakdown.disable_constraints():
        if affected_divisions_ids:
            DivisionPartyBreakdown.objects.filter(
                division_id__in=affected_divisions_ids
            ).delete()
        else:
            DivisionPartyBreakdown.objects.all().delete()
        DivisionPartyBreakdown.objects.bulk_create(to_create, batch_size=50000)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] party breakdowns")

    to_create = []
    df = pd.read_parquet(divisions_gov_with_counts)

    for _, row in df.iterrows():
        # only create for new divisions
        if (
            affected_divisions_ids
            and division_key_to_id[row["division_id"]] not in affected_divisions_ids
        ):
            continue
        to_create.append(
            DivisionsIsGovBreakdown(
                division_id=division_key_to_id[row["division_id"]],
                is_gov=row["grouping"],
                vote_participant_count=row["vote_participant_count"],
                total_possible_members=row["total_possible_members"],
                for_motion=row["for_motion"],
                against_motion=row["against_motion"],
                neutral_motion=row["neutral_motion"],
                absent_motion=row["absent_motion"],
                signed_votes=row["signed_votes"],
                motion_majority=row["motion_majority"],
                for_motion_percentage=row["for_motion_percentage"],
                motion_result_int=row["motion_result_int"],
            )
        )

    with DivisionsIsGovBreakdown.disable_constraints():
        if affected_divisions_ids:
            DivisionsIsGovBreakdown.objects.filter(
                division_id__in=affected_divisions_ids
            ).delete()
        else:
            DivisionsIsGovBreakdown.objects.all().delete()
        DivisionsIsGovBreakdown.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] government breakdowns")
