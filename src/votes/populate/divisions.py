import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug
from ..models.decisions import Chamber, Division
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


BASE_DIR = Path(settings.BASE_DIR)


@duck.as_source
class pw_divisions:
    source = BASE_DIR / "data" / "source" / "divisions.parquet"


@duck.as_source
class api_divisions:
    source = BASE_DIR / "data" / "compiled" / "api_divisions.parquet"


@duck.as_alias
class org_membership_count:
    alias_for = "postgres_db.votes_orgmembershipcount"


@duck.as_view
class divisions_with_total_membership:
    query = """
        SELECT
            pw_divisions.*,
            org_membership_count.count as total_possible_members
        FROM
            pw_divisions
        LEFT JOIN org_membership_count on
            (pw_divisions.division_date between org_membership_count.start_date
            and org_membership_count.end_date
            and pw_divisions.chamber = org_membership_count.chamber_slug)
        WHERE
            pw_divisions.chamber != 'pbc'
            and division_id not like '%cy-senedd'
        """


@duck.as_view
class api_divisions_with_total_membership:
    query = """
        SELECT
            api_divisions.*,
            org_membership_count.count as total_possible_members
        FROM
            api_divisions
        LEFT JOIN org_membership_count on
            (CAST(api_divisions.division_date as DATE) between org_membership_count.start_date
            and org_membership_count.end_date
            and api_divisions.chamber = org_membership_count.chamber_slug)
        """


def add_ellipsis(text: str, max_length: int = 255) -> str:
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def division_from_row(
    row: pd.Series, chamber_id_lookup: dict[ChamberSlug, int]
) -> Division:
    return Division(
        key=row["division_id"],
        chamber_slug=ChamberSlug(row["chamber"]),
        chamber_id=chamber_id_lookup[ChamberSlug(row["chamber"])],
        source_gid=row["source_gid"],
        debate_gid=row["debate_gid"],
        division_name=add_ellipsis(row["division_title"]),
        date=row["division_date"],
        division_number=row["division_number"],
        total_possible_members=row["total_possible_members"],
    )


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
        division_from_row(row, chamber_id_lookup=chamber_lookup)
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

    to_create = Division.get_lookup_manager("key").add_ids(to_create)
    with Division.disable_constraints():
        to_delete.delete()
        Division.objects.bulk_create(to_create, batch_size=10000)
        Division.objects.bulk_create(api_to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] divisions")
        rich.print(f"Imported [green]{len(api_to_create)}[/green] api divisions")
