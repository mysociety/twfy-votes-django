import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery

from ..consts import VotePosition
from ..models import Division, Vote
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")

votes_with_parties = compiled_dir / "votes_with_parties.parquet"
votes_with_diff = compiled_dir / "votes_with_diff.parquet"
divisions_party_with_counts = compiled_dir / "divisions_party_with_counts.parquet"
existing_votes = compiled_dir / "existing_votes.parquet"

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


@duck.as_alias
class ps_votes:
    alias_for = "postgres_db.votes_vote"


@duck.as_macro
class str_to_int_vote_position:
    """
    See VotePosition Const
    """

    args = ["str_vote_position"]
    macro = """
    CASE str_vote_position
        WHEN 'aye' THEN 1
        WHEN 'no' THEN 2
        WHEN 'abstain' THEN 3
        WHEN 'absent' THEN 4
        WHEN 'tellno' THEN 5
        WHEN 'tellaye' THEN 6
        WHEN 'collective' THEN 7
        ELSE null
    END
    """


@duck.to_parquet(dest=existing_votes)
class ps_existing_votes:
    """
    Get existing votes from the database
    """

    query = """
    SELECT
        id,
        division_id,
        person_id,
    FROM
        ps_votes
    """


@duck.to_parquet(dest=votes_with_diff)
class pw_votes_with_party_difference:
    """
    Update the votes table to include difference from the party average for each vote.
    """

    query = """
    SELECT
        cm_votes_with_people.* exclude(total_possible_members, division_id, vote, effective_vote),
        str_to_int_vote_position(cm_votes_with_people.vote) as vote,
        str_to_int_vote_position(cm_votes_with_people.effective_vote) as effective_vote,
        ps_divisions.id as division_id,
        effective_vote_float:
            case cm_votes_with_people.effective_vote
                when 'aye' then 1
                when 'no' then 0
                when 'abstain' then 0.5
            end,
        diff_from_party_average:
            case 
                when cm_votes_with_people.effective_party_slug = 'independent' then null
                else abs(effective_vote_float - for_motion_percentage)
            end
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


def extend_ids(col: pd.Series) -> pd.Series:
    """
    Given a series of ids, and some Nones,
    add new ids starting from the max of the existing ids
    """

    max_id = col.max()
    if pd.isna(max_id):
        max_id = 0
    max_id += 1

    def add_id(x):
        nonlocal max_id
        if pd.isna(x):
            x = max_id
            max_id += 1
        return x

    col = col.apply(add_id)

    return col


def create_full_table(quiet: bool = False):
    # this is such a big table we're skipping the pydantic validation step
    # doing a basic set of checks on things not imposed by types

    df = pd.read_parquet(votes_with_diff)

    # for consistency, we need to get the existing ids
    df_existing = pd.read_parquet(existing_votes)

    # join to get ids where they already exist
    df = df.merge(df_existing, on=["division_id", "person_id"], how="left")

    # now we need to add ids for the new votes - starting at the current max
    df["id"] = extend_ids(df["id"])

    df.to_parquet(votes_with_diff, index=False)

    # test that we've only got valid vote positions
    # at this point
    for vote_option in df["vote"].unique():
        VotePosition(vote_option)

    for effective_vote in df["effective_vote"].unique():
        VotePosition(effective_vote)

    # now we're just sucking the data straight into the database from
    # parquet
    start = datetime.datetime.now()
    count = Vote.replace_with_parquet(votes_with_diff)
    end = datetime.datetime.now()
    seconds = (end - start).total_seconds()

    if not quiet:
        rich.print(
            f"Created [green]{count}[/green] votes in the database (took {seconds:.2f}s)"
        )


@import_register.register("votes", group=ImportOrder.VOTES)
def import_votes(quiet: bool = False, update_since: datetime.date | None = None):
    # better on memory to write straight out as parquet, close duckdb and read in the parquet
    with DuckQuery.connect() as query:
        query.compile(duck).run()

    if not update_since:
        """
        If not update_since, we want to create the full table.
        """
        create_full_table()
        return

    # get divisions since the last update

    rel_division_ids = Division.objects.filter(date__gte=update_since).values_list(
        "id", flat=True
    )

    # reduce to just the votes associated with the new divisions
    df = pd.read_parquet(votes_with_diff)
    df = df[df["division_id"].isin(rel_division_ids)]

    to_create = []

    existing_relevant_votes = Vote.objects.filter(division_id__in=rel_division_ids)
    lookup = {f"{x.division_id}-{x.person_id}": x.id for x in existing_relevant_votes}
    last_id = Vote.objects.all().order_by("-id").first()
    if last_id:
        max_id = int(last_id.id)  # type: ignore
    else:
        max_id = int(1)

    def get_id(key: str):
        nonlocal max_id
        if key in lookup:
            return lookup[key]
        max_id += 1
        return max_id

    for _, row in df.iterrows():
        to_create.append(
            Vote(
                id=get_id(f"{row['division_id']}-{row['person_id']}"),
                division_id=row["division_id"],
                person_id=row["person_id"],
                vote=row["vote"],
                effective_vote=row["effective_vote"],
                membership_id=row["membership_id"],
                is_gov=row["is_gov"],
                effective_vote_float=row["effective_vote_float"],
                diff_from_party_average=row["diff_from_party_average"],
            )
        )

    # Bulk create votes
    Vote.objects.filter(division_id__in=rel_division_ids).delete()
    Vote.objects.bulk_create(to_create)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] votes")
