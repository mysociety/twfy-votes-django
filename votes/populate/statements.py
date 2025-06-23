import datetime
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.template.defaultfilters import slugify

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug, StatementType
from ..models import Chamber, Statement
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
DATA_DIR = BASE_DIR / "data" / "source"


class DuplicateSlugManager:
    """
    This only checks duplicates within a run - but this should be fine because
    even the partial reimport will always reimport the whole of a day.
    """

    def __init__(self):
        self.slugs = set()

    def check(self, slug: str, date: datetime.date) -> str:
        """
        Check if the slug is unique, and if not, append a number to make it unique.
        """
        original_slug = slug
        counter = 2
        while (date, slug) in self.slugs:
            slug = f"{original_slug}-{counter}"
            counter += 1
        self.slugs.add((date, slug))
        return slug


def load_commons_edms(quiet: bool, update_since: datetime.date | None):
    """
    Load House of Commons EDMs
    """
    if update_since:
        timestamp = pd.Timestamp(update_since)
    else:
        timestamp = None

    df = pd.read_parquet(DATA_DIR / "proposals.parquet")

    df["date_tabled"] = pd.to_datetime(df["date_tabled"])
    if timestamp is not None:
        df = df[df["date_tabled"] >= timestamp]

    chamber_slug = ChamberSlug.COMMONS
    chamber = Chamber.objects.get(slug=chamber_slug)
    chamber_id = chamber.id
    if chamber_id is None:
        raise ValueError(f"Chamber with slug {chamber_slug} not found")

    to_create: list[Statement] = []

    direct_fields = ["id", "title", "motion_text", "date_tabled"]
    other_fields = [x for x in df.columns if x not in direct_fields]

    slug_dup_manager = DuplicateSlugManager()

    for _, row in df.iterrows():
        extra_info = {
            field: row[field] for field in other_fields if pd.notna(row[field])
        }
        date = row["date_tabled"].date()
        slugified_title = slugify(row["title"])[:50]
        original_id = str(row["id"])
        key = f"s-{chamber_slug}-{date}-{original_id}-{slugified_title}"
        url = f"https://edm.parliament.uk/early-day-motion/{row['id']}"
        slug = slug_dup_manager.check(slugify(row["title"]), date=date)

        statement = Statement(
            original_id=original_id,
            slug=slug,
            title=row["title"],
            statement_text=row["motion_text"],
            type=StatementType.PROPOSED_MOTION,
            chamber_slug=chamber_slug,
            chamber_id=chamber_id,
            date=date,
            key=key,
            url=url,
            info_source="house_of_commons_edm",
            extra_info=extra_info,
        )

        to_create.append(statement)

    # check for duplicate keys in to_create
    keys = [x.key for x in to_create]
    if len(keys) != len(set(keys)):
        duplicate_keys = [
            k for k, v in Counter(keys).items() if v > 1 and k is not None
        ]
        if duplicate_keys:
            raise ValueError(f"Duplicate keys found in to_create: {duplicate_keys}")

    to_create = Statement.get_lookup_manager("key").add_ids(to_create)

    to_delete = Statement.objects.filter(
        chamber=chamber, info_source="house_of_commons_edm"
    )
    if update_since:
        to_delete = to_delete.filter(date__gte=update_since)

    # wrap in transaction to roll back safely
    with transaction.atomic():
        to_delete.delete()
        Statement.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(
            f"Loaded {len(to_create)} House of Commons EDMs from {DATA_DIR / 'proposals.parquet'}"
        )


@import_register.register("statements", group=ImportOrder.DECISIONS)
def import_divisions(quiet: bool = False, update_since: datetime.date | None = None):
    load_commons_edms(quiet=quiet, update_since=update_since)
