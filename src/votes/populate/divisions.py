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


@duck.as_alias
class org_membership_count:
    alias_for = "postgres_db.votes_orgmembershipcount"


@duck.as_query
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
def import_divisions(quiet: bool = False):
    df = DuckQuery.connect().compile(duck).df()

    chamber_lookup = {x.slug: x.id for x in Chamber.objects.all() if x.id}
    to_create = [
        division_from_row(row, chamber_id_lookup=chamber_lookup)
        for _, row in df.iterrows()
    ]

    to_create = Division.get_lookup_manager("key").add_ids(to_create)
    with Division.disable_constraints():
        Division.objects.all().delete()
        Division.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] divisions")
