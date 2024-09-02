from pathlib import Path

from django.conf import settings

from twfy_votes.helpers.duck import DuckQuery

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


@duck.to_parquet(dest=votes_with_diff)
class pw_votes_with_party_difference:
    """
    Update the votes table to include difference from the party average for each vote.
    """

    query = """
    SELECT
        cm_votes_with_people.*,
        for_motion_percentage,
        case effective_vote
            when 'aye' then 1
            when 'no' then 0
            when 'abstention' then 0.5
        end as effective_vote_int,
        abs(effective_vote_int - for_motion_percentage) as diff_from_party_average
    FROM
        cm_votes_with_people
    JOIN
        pw_divisions_party_with_counts
            on
                (cm_votes_with_people.division_id = pw_divisions_party_with_counts.division_id and
                 cm_votes_with_people.effective_party_slug = pw_divisions_party_with_counts.grouping)
    """


@import_register.register("votes", group=ImportOrder.VOTES)
def import_votes(quiet: bool = False):
    # better on memory to write straight out as parquet, close duckdb and read in the parquet
    with DuckQuery.connect() as query:
        query.compile(duck).run()
