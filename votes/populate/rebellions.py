from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import RebellionPeriodType
from ..models import RebellionRate
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)

VOTES_WITH_DIFF_PATH = BASE_DIR / "data" / "compiled" / "votes_with_diff.parquet"
PER_PERSON_ALL_TIME_PATH = (
    BASE_DIR / "data" / "compiled" / "per_person_party_diff_all_time.parquet"
)
PER_PERSON_YEAR_PATH = (
    BASE_DIR / "data" / "compiled" / "per_person_party_diff_year.parquet"
)
PER_PERSON_PERIOD_PATH = (
    BASE_DIR / "data" / "compiled" / "per_person_party_diff_period.parquet"
)

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_source
class votes_with_diff:
    source = VOTES_WITH_DIFF_PATH


@duck.as_alias
class pw_division:
    alias_for = "postgres_db.votes_division"


@duck.as_view
class party_diff_over_time:
    query = """
    SELECT
        votes_with_diff.person_id,
        diff_from_party_average,
        year: date_part('year', pw_division.date),
        in_last_x_year: cast(ceiling(( current_date - pw_division.date) / 365) as int)
    from
        votes_with_diff
    join
        pw_division on votes_with_diff.division_id = pw_division.id
    """


@duck.to_parquet(PER_PERSON_ALL_TIME_PATH)
class per_person_party_diff_all_time:
    query = """
    SELECT
        person_id,
        avg_diff_from_party: avg(diff_from_party_average),
        total_votes: count(*)
    from
        party_diff_over_time
    group by
        all
    """


@duck.to_parquet(PER_PERSON_YEAR_PATH)
class per_person_party_diff_year:
    query = """
    SELECT
        person_id,
        year,
        avg_diff_from_party: avg(diff_from_party_average),
        total_votes: count(*)
    from
        party_diff_over_time
    group by
        all
    """


@duck.to_parquet(PER_PERSON_PERIOD_PATH)
class per_person_party_diff_period:
    query = """
    SELECT
        person_id,
        in_last_x_year,
        avg_diff_from_party: avg(diff_from_party_average),
        total_votes: count(*)
    from
        party_diff_over_time
    group by
        all
    """


@import_register.register("rebellions", group=ImportOrder.PERSON_STATS)
def import_rebellions(quiet: bool = False):
    with DuckQuery.connect() as query:
        query.compile(duck).run()

    to_create = []

    df = pd.read_parquet(PER_PERSON_ALL_TIME_PATH)

    for _, row in df.iterrows():
        to_create.append(
            RebellionRate(
                person_id=row["person_id"],
                period_number=0,
                period_type=RebellionPeriodType.ALLTIME,
                value=row["avg_diff_from_party"],
                total_votes=row["total_votes"],
            )
        )

    df = pd.read_parquet(PER_PERSON_YEAR_PATH)

    for _, row in df.iterrows():
        to_create.append(
            RebellionRate(
                person_id=row["person_id"],
                period_number=row["year"],
                period_type=RebellionPeriodType.YEAR,
                value=row["avg_diff_from_party"],
                total_votes=row["total_votes"],
            )
        )

    df = pd.read_parquet(PER_PERSON_PERIOD_PATH)

    for _, row in df.iterrows():
        to_create.append(
            RebellionRate(
                person_id=row["person_id"],
                period_number=row["in_last_x_year"],
                period_type=RebellionPeriodType.PERIOD,
                value=row["avg_diff_from_party"],
                total_votes=row["total_votes"],
            )
        )

    existing_keys = {x.composite_key(): x.id for x in RebellionRate.objects.all()}

    for item in to_create:
        key = item.composite_key()
        if key in existing_keys:
            item.id = existing_keys[key]

    RebellionRate.objects.all().delete()
    RebellionRate.objects.bulk_create(to_create)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] rebellion rates")
