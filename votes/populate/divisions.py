from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from ..consts import AyeNo, ChamberSlug
from ..models import Chamber, Division
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)


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
        yes_total=row["yes_total"],
        no_total=row["no_total"],
        abstain_total=row["both_total"],
        absent_total=row["absent_total"],
        majority_vote=AyeNo(row["majority_vote"]),
    )


@import_register.register("divisions", group=ImportOrder.DECISIONS)
def import_divisions(quiet: bool = False):
    divisions_file = BASE_DIR / "data" / "source" / "divisions.parquet"

    if not divisions_file.exists():
        raise FileNotFoundError(f"Could not find divisions file at {divisions_file}")

    df = pd.read_parquet(divisions_file)

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
