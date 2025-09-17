import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug
from ..models import Chamber, Signature, Statement
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
DATA_DIR = BASE_DIR / "data" / "source"


def load_commons_edms(quiet: bool = False, update_since: datetime.date | None = None):
    """
    Load House of Commons EDMs
    """
    if update_since:
        timestamp = pd.Timestamp(update_since)
    else:
        timestamp = None

    df = pd.read_parquet(DATA_DIR / "signatures.parquet")

    # remove duplicates based on member_id and proposal_id
    df = df.drop_duplicates(subset=["member_id", "proposal_id"])

    df["created_when"] = pd.to_datetime(df["created_when"])
    if timestamp is not None:
        df = df[df["created_when"] >= timestamp]

    chamber_slug = ChamberSlug.COMMONS
    chamber = Chamber.objects.get(slug=chamber_slug)
    chamber_id = chamber.id
    if chamber_id is None:
        raise ValueError(f"Chamber with slug {chamber_slug} not found")

    statement_id_lookup = Statement.id_from_slugs("chamber_slug", "original_id")

    to_create: list[Signature] = []

    direct_fields = [
        "id",
        "member_id",
        "proposal_id",
        "sponsoring_order",
        "created_when",
        "twfy_id",
        "is_withdrawn",
        "withdrawn_date",
    ]
    other_fields = [x for x in df.columns if x not in direct_fields]

    for _, row in df.iterrows():
        if pd.isna(row["twfy_id"]):
            continue

        key = (chamber_slug, str(row["proposal_id"]))
        statement_id = statement_id_lookup.get(key)
        if statement_id is None:
            raise ValueError(
                f"Statement not found for chamber_slug={chamber_slug}, proposal_id={row['proposal_id']}"
            )

        extra_info = {
            field: row[field] for field in other_fields if pd.notna(row[field])
        }

        key = f"commons-edm-{statement_id}-{row['id']}"

        date = row["created_when"].date()
        if pd.isnull(date):
            date = None
        withdrawn_date = row["withdrawn_date"].date()
        if pd.isnull(withdrawn_date):
            withdrawn_date = None
        order = row["sponsoring_order"]
        if pd.isna(order):
            order = 999
        else:
            order = int(order)

        signature = Signature(
            key=key,
            statement_id=statement_id,
            person_id=row["twfy_id"],
            date=date,
            order=order,
            withdrawn=row["is_withdrawn"],
            withdrawn_date=withdrawn_date,
            extra_info=extra_info,
        )

        to_create.append(signature)

    to_create = Signature.get_lookup_manager("key").add_ids(to_create)

    to_delete = Signature.objects.filter(
        statement__chamber=chamber,
        statement__info_source="house_of_commons_edm",
    )

    if update_since:
        to_delete = to_delete.filter(date__gte=update_since)

    to_delete.delete()

    Signature.objects.bulk_create(to_create, batch_size=10000)
    if not quiet:
        rich.print(f"Imported {len(to_create)} signatures for {chamber_slug} EDMs")


@import_register.register("signatures", group=ImportOrder.SIGNATURES)
def import_divisions(quiet: bool = False, update_since: datetime.date | None = None):
    load_commons_edms(update_since=update_since)
