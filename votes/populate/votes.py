from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery, sync_to_postgres

from ..consts import VotePosition
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")

votes_with_parties = compiled_dir / "votes_with_parties.parquet"
votes_with_diff = compiled_dir / "votes_with_diff.parquet"
divisions_party_with_counts = compiled_dir / "divisions_party_with_counts.parquet"


duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_source
class cm_votes_with_people:
    source = votes_with_parties


@duck.as_source
class pw_divisions_party_with_counts:
    source = divisions_party_with_counts


@duck.as_alias
class ps_divisions:
    alias_for = "postgres_db.votes_division"


@duck.to_parquet(dest=votes_with_diff)
class pw_votes_with_party_difference:
    """
    Update the votes table to include difference from the party average for each vote.
    """

    query = """
    SELECT
        row_number() over() as id,
        cm_votes_with_people.* exclude(total_possible_members, division_id),
        ps_divisions.id as division_id,
        case effective_vote
            when 'aye' then 1
            when 'no' then 0
            when 'abstain' then 0.5
        end as effective_vote_float,
        COALESCE(abs(effective_vote_float - for_motion_percentage), 0) as diff_from_party_average
    FROM
        cm_votes_with_people
    JOIN
        pw_divisions_party_with_counts
            on
                (cm_votes_with_people.division_id = pw_divisions_party_with_counts.division_id and
                 cm_votes_with_people.effective_party_slug = pw_divisions_party_with_counts.grouping)
    JOIN ps_divisions 
        on cm_votes_with_people.division_id = ps_divisions.key
    """


@import_register.register("votes", group=ImportOrder.VOTES)
def import_votes(quiet: bool = False):
    # better on memory to write straight out as parquet, close duckdb and read in the parquet
    with DuckQuery.connect() as query:
        query.compile(duck).run()

    # this is such a big table we're skipping the pydantic validation step
    # doing a basic set of checks on things not imposed by types

    df = pd.read_parquet(votes_with_diff)

    # test that we've only got valid vote positions
    # at this point
    for vote_option in df["vote"].unique():
        VotePosition(vote_option)

    for effective_vote in df["effective_vote"].unique():
        VotePosition(effective_vote)

    # now we're just sucking the data straight into the database from
    # parquet
    count = sync_to_postgres(
        votes_with_diff, "votes_vote", settings.DATABASES["default"]
    )

    if not quiet:
        rich.print(f"Created [green]{count}[/green] votes in the database")
