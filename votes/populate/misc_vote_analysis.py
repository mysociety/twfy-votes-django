from __future__ import annotations

import datetime
from pathlib import Path

from django.conf import settings

from twfy_votes.helpers.duck import DuckQuery

from ..consts import TagType, VotePosition
from ..models import DecisionTag, DivisionTagLink
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")

divisions_gov_with_counts = compiled_dir / "divisions_gov_with_counts.parquet"
votes_with_diff = compiled_dir / "votes_with_diff.parquet"

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_source
class cm_votes_with_people:
    source = votes_with_diff


@duck.as_alias
class pw_division:
    alias_for = "postgres_db.votes_division"


@duck.as_source
class pw_divisions_gov_with_counts:
    source = divisions_gov_with_counts


@duck.as_table
class vote_division_pivot:
    query = """
    SELECT
        vote_pivot.*,
        division.division_name AS title,
        division.date AS date
    FROM
        vote_pivot: (pivot cm_votes_with_people ON vote GROUP BY division_id)
    JOIN
        division: pw_division on (vote_pivot.division_id = division.id)
    """


class false_aye_tellers:
    """
    By this point the VotePositons have been converted to integers, which are the columns of the pivot.
    """

    query = f"""
    SELECT
        *
    FROM
        vote_division_pivot
    WHERE
       \"{VotePosition.TELLAYE}\" > 0 AND \"{VotePosition.AYE}\" = 0 AND \"{VotePosition.ABSTAIN}\" = 0
    """


class false_no_tellers:
    query = f"""
    SELECT
        *
    FROM
        vote_division_pivot
    WHERE
       \"{VotePosition.TELLNO}\" > 0 AND \"{VotePosition.NO}\" = 0 AND \"{VotePosition.ABSTAIN}\" = 0
    """


class drawn_results:
    query = f"""
    SELECT
        *
    FROM
        vote_division_pivot
    WHERE
      \"{VotePosition.AYE}\" == \"{VotePosition.NO}\"
    """


@import_register.register("misc_vote_analysis", group=ImportOrder.DIVISION_ANALYSIS)
def vote_analysis(quiet: bool = False, update_since: datetime.date | None = None):
    with DuckQuery.connect() as query:
        query.compile(duck).run()
        false_no_tellers_df = query.compile(false_no_tellers).df()
        false_aye_tellers_df = query.compile(false_aye_tellers).df()
        drawn_results_df = query.compile(drawn_results).df()

    DivisionTagLink.sync_tag_from_division_id_list(
        DecisionTag.objects.get(tag_type=TagType.MISC, slug="false_no_tellers"),
        false_no_tellers_df["division_id"].tolist(),
        quiet=quiet,
    )

    DivisionTagLink.sync_tag_from_division_id_list(
        DecisionTag.objects.get(tag_type=TagType.MISC, slug="false_aye_tellers"),
        false_aye_tellers_df["division_id"].tolist(),
        quiet=quiet,
    )

    DivisionTagLink.sync_tag_from_division_id_list(
        DecisionTag.objects.get(tag_type=TagType.MISC, slug="tie"),
        drawn_results_df["division_id"].tolist(),
        quiet=quiet,
    )
