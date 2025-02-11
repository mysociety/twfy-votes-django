from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug
from ..models import Agreement, Chamber
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)

AGREEMENT_PATH = BASE_DIR / "data" / "source" / "motions.parquet"


duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)


@duck.as_source
class pw_agreements:
    source = BASE_DIR / "data" / "source" / "agreements.parquet"


@duck.as_alias
class motions:
    alias_for = "postgres_db.votes_motion"


@duck.as_view
class agreement_with_motion_id:
    query = """
    SELECT
        pw_agreements.*,
        motions.id as motion_id
    from pw_agreements
    left join motions on
        (pw_agreements.motion_gid = motions.gid)
    """


def add_ellipsis(text: str, max_length: int = 255) -> str:
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


@import_register.register("agreements", group=ImportOrder.DECISIONS)
def import_agreements(quiet: bool = False):
    with DuckQuery.connect() as cduck:
        cduck.compile(duck).run()
        df = cduck.compile(agreement_with_motion_id).df()

    chamber_ids = Chamber.id_from_slug("slug")

    # set nan in the negative column to False
    df["negative"] = df["negative"].fillna(False)

    to_create = []
    for index, row in df.iterrows():
        chamber_slug = ChamberSlug(ChamberSlug.from_parlparse(row["chamber"]))
        chamber_id = chamber_ids[chamber_slug]
        safe_pid = row["gid"].split("/")[-1][10:]

        item = Agreement(
            key=f"a-{chamber_slug}-{row['date']}-{safe_pid}",
            chamber_slug=chamber_slug,
            chamber_id=chamber_id,
            date=row["date"],
            negative=row["negative"],
            decision_ref=safe_pid,
            decision_name=row["motion_title"],
            motion_id=int(row["motion_id"]) if not pd.isna(row["motion_id"]) else None,
        )

        to_create.append(item)

    to_create = Agreement.get_lookup_manager("key").add_ids(to_create)

    Agreement.objects.all().delete()
    Agreement.objects.bulk_create(to_create, batch_size=1000)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] agreements")
