import datetime
from collections import Counter
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug
from ..models import Chamber, Division
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


BASE_DIR = Path(settings.BASE_DIR)


@duck.as_source
class pw_divisions:
    source = BASE_DIR / "data" / "source" / "divisions.parquet"


@duck.as_source
class division_links:
    source = BASE_DIR / "data" / "source" / "division-links.parquet"


@duck.as_source
class api_divisions:
    source = BASE_DIR / "data" / "compiled" / "api_divisions.parquet"


@duck.as_alias
class org_membership_count:
    alias_for = "postgres_db.votes_orgmembershipcount"


@duck.as_alias
class motions:
    alias_for = "postgres_db.votes_motion"


@duck.as_view
class division_links_with_id:
    query = """
    SELECT
        division_links.*,
        motions.id as motion_id
    from division_links
    join motions on
        (division_links.motion_gid = motions.gid)
    """


@duck.as_view
class divisions_with_total_membership:
    query = """
        SELECT
            pw_divisions.*,
            org_membership_count.count as total_possible_members,
            division_links_with_id.motion_id as motion_id,
            'twfy' as division_info_source
        FROM
            pw_divisions
        LEFT JOIN org_membership_count on
            (pw_divisions.division_date between org_membership_count.start_date
            and org_membership_count.end_date
            and pw_divisions.chamber = org_membership_count.chamber_slug)
        LEFT JOIN division_links_with_id on
            (pw_divisions.source_gid = division_links_with_id.division_gid)
        WHERE
            pw_divisions.chamber != 'pbc'
            and division_id not like '%cy-senedd'
        """


@duck.as_view
class api_divisions_with_total_membership:
    query = """
        SELECT
            api_divisions.*,
            org_membership_count.count as total_possible_members,
            'commons_api' as division_info_source
        FROM
            api_divisions
        LEFT JOIN org_membership_count on
            (CAST(api_divisions.division_date as DATE) between org_membership_count.start_date
            and org_membership_count.end_date
            and CAST(api_divisions.chamber as STRING) = org_membership_count.chamber_slug)
        """


def add_ellipsis(text: str, max_length: int = 255) -> str:
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def division_from_row(
    row: pd.Series,
    chamber_id_lookup: dict[ChamberSlug, int],
    add_motion_id: bool = True,
) -> Division:
    if add_motion_id:
        motion_id = row["motion_id"]
        if pd.isna(motion_id):
            motion_id = None
        else:
            motion_id = int(motion_id)
    else:
        motion_id = None

    d = Division(
        key=row["division_id"],
        chamber_slug=ChamberSlug(row["chamber"]),
        chamber_id=chamber_id_lookup[ChamberSlug(row["chamber"])],
        source_gid=row["source_gid"],
        debate_gid=row["debate_gid"] or "",
        division_name=add_ellipsis(row["division_title"]),
        date=row["division_date"],
        division_number=row["division_number"],
        total_possible_members=row["total_possible_members"],
        division_info_source=row["division_info_source"],
        motion_id=motion_id,
    )

    return d


@import_register.register("divisions", group=ImportOrder.DECISIONS)
def import_divisions(quiet: bool = False, update_since: datetime.date | None = None):
    if update_since:
        timestamp = pd.Timestamp(update_since)
    else:
        timestamp = None
    with DuckQuery.connect() as cduck:
        cduck.compile(duck).run()
        df = cduck.compile("SELECT * from divisions_with_total_membership").df()
        votes_api_df = cduck.compile(
            "SELECT * from api_divisions_with_total_membership"
        ).df()

    chamber_lookup = {x.slug: x.id for x in Chamber.objects.all() if x.id}
    to_create = [
        division_from_row(row, chamber_id_lookup=chamber_lookup)
        for _, row in df.iterrows()
        if timestamp is None or row["division_date"] >= timestamp
    ]

    api_to_create = [
        division_from_row(row, chamber_id_lookup=chamber_lookup, add_motion_id=False)
        for _, row in votes_api_df.iterrows()
        if timestamp is None or row["division_date"] >= timestamp
    ]

    # remove any api divisions that are already in the main divisions based on key
    api_to_create = [
        x for x in api_to_create if x.key not in [y.key for y in to_create]
    ]

    if update_since:
        to_delete = Division.objects.filter(date__gte=update_since)
    else:
        to_delete = Division.objects.all()

    # need to check for duplicate keys in to_create
    keys = [x.key for x in to_create]

    if len(keys) != len(set(keys)):
        duplicate_keys = [
            k for k, v in Counter(keys).items() if v > 1 and k is not None
        ]
        if duplicate_keys:
            raise ValueError(f"Duplicate keys found in to_create: {duplicate_keys}")

    to_create = Division.get_lookup_manager("key").add_ids(to_create)
    api_to_create = Division.get_lookup_manager("key").add_ids(api_to_create)

    with Division.disable_constraints():
        to_delete.delete()
        Division.objects.bulk_create(to_create, batch_size=10000)
        Division.objects.bulk_create(api_to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] divisions")
        rich.print(f"Imported [green]{len(api_to_create)}[/green] api divisions")
