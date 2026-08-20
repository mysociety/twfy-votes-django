"""
Orchestration and data sources for the set-based policy calculation.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from django.conf import settings

import rich

from twfy_votes.helpers.duck import DuckQuery, DuckResponse
from twfy_votes.helpers.duck.core import ConnectedDuckQuery
from twfy_votes.helpers.duck.funcs import query_to_parquet
from votes.models import VoteDistribution

from .policycalc_query import scored_bulk_policy_query
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")


@duck.as_source
class policy_divisions_relevant:
    source = compiled_dir / "policy_divisions_relevant.parquet"


@duck.as_source
class policy_agreements_relevant:
    source = compiled_dir / "policy_agreements_relevant.parquet"


@duck.as_source
class policy_votes_relevant:
    source = compiled_dir / "policy_votes_relevant.parquet"


@duck.as_source
class policy_collective_relevant:
    source = compiled_dir / "policy_collective_relevant.parquet"


@duck.as_alias
class pd_memberships_source:
    alias_for = "postgres_db.votes_membership"


@duck.as_source
class pw_relevant_people:
    source = compiled_dir / "relevant_person_policy_period.parquet"


@duck.as_table
class pd_memberships:
    query = """
    select * from pd_memberships_source
    where person_id in (select distinct person_id from pw_relevant_people)
    order by start_date
    """


@duck.as_alias
class policies:
    alias_for = "postgres_db.votes_policy"


# so if we load before any files exist it's ok to create
compiled_policy_output = compiled_dir / "policy_calc_to_load.parquet"
if compiled_policy_output.exists():

    @duck.as_source
    class compiled_policies_source:  # type: ignore
        source = compiled_policy_output

    @duck.as_view
    class compiled_policies:  # type: ignore
        query = """
        select
            * exclude (party_id),
            coalesce(party_id, 0) as party_id
        from compiled_policies_source
        """

else:
    # create an equiv empty table with these
    # columns person_id, period_id, policy_id, party_id, policy_hash

    @duck.as_view
    class compiled_policies:
        query = """
        select
            person_id: null,
            period_id: null,
            policy_id: null,
            party_id: null,
            policy_hash: null 
        where 1 = 0
        """


@duck.as_source
class relevant_person_policy_period:
    source = compiled_dir / "relevant_person_policy_period.parquet"


@duck.as_view
class policy_hash:
    """
    This is a hash of the policy table
    """

    query = """
    select
        policy_id: id,
        policy_hash
    from
        policies
    """


@duck.as_view
class relevant_person_policy_period_with_hash:
    """
    This should be all possible connections of people and policies - with a hash.
    """

    query = """
    select
        relevant_person_policy_period.* exclude (party_id),
        party_id: coalesce(party_id, 0),
        policy_hash.policy_hash
    from
        relevant_person_policy_period
    join
        policy_hash using (policy_id)
        """


@duck.as_view
class compare_hash:
    """
    This is a hash of the comparison party table.
    This helps us find differences between the compiled and the current.
    """

    query = """
    select
        person_id: rp.person_id,
        chamber_id: rp.chamber_id,
        period_id: rp.period_id,
        policy_id: rp.policy_id,
        party_id: rp.party_id,
        current_hash: rp.policy_hash,
        compiled_hash: compiled_policies.policy_hash,
        hash_differs: current_hash != compiled_hash
    from 
        relevant_person_policy_period_with_hash as rp
    left join
        compiled_policies using (person_id, period_id, policy_id, party_id)
        
    """


def get_connected_duck() -> ConnectedDuckQuery[DuckResponse]:
    connected = DuckQuery.connect()
    # Keep the bulk query below the worker's memory ceiling; DuckDB spills large
    # hash aggregates to its temporary directory when necessary.
    connected.connection.execute("set memory_limit = '2.5GB'")
    connected.compile(duck).run()
    return connected


def check_generated_against_current() -> list[int]:
    """
    Return a list of person_ids where the policy distributions differ from the compiled.
    """
    duck = get_connected_duck()
    df = duck.get_view(compare_hash).df()

    # if hash_differs isna - it should be True
    df["hash_differs_na_or_false"] = df["hash_differs"].isna() | (
        df["hash_differs"] == True  # noqa
    )

    # reduce to just those with hash differs
    df = df[df["hash_differs_na_or_false"]]
    return df["person_id"].unique().tolist()


def generate_combo_with_id(source: Path, dest: Path) -> None:
    """
    Create a parquet file with all the items for copying into the database
    """
    query = f"""
    select
        row_number() over() as id,
        compiled_policies.* exclude (party_id),
        case party_id when 0 then null else party_id end as party_id
    from '{source}' as compiled_policies
    """
    with DuckQuery.connect() as duck:
        duck.compile(query_to_parquet(query, dest=dest)).run()


def generate_policy_distributions(
    update_from_hash: bool = False,
    person_ids: list[int] | None = None,
    policy_ids: list[int] | None = None,
    quiet: bool = False,
) -> int:
    """
    This generates voting summaries for everyone.
    It can be limited by person_ids or policy_ids.
    Limiting by policy_ids still regenerates all policies for affected people,
    but doesn't regenerate for people who don't have that policy.
    """

    duck = get_connected_duck()
    if update_from_hash and person_ids is None:
        person_ids = check_generated_against_current()
        if not person_ids:
            return 0

    filters = []
    if person_ids:
        filters.append(f"person_id in ({','.join(str(int(x)) for x in person_ids)})")
    if policy_ids:
        # Select people connected to these policies, then regenerate all of their policies.
        filters.append(f"policy_id in ({','.join(str(int(x)) for x in policy_ids)})")
    target_filter = f"where {' and '.join(filters)}" if filters else ""

    combined_dest = compiled_dir / "policy_calc_combined.parquet"
    combined_dest.unlink(missing_ok=True)
    scored_query = scored_bulk_policy_query(target_filter)
    final_query = f"""
        select
            row_number() over () as id,
            scored.* exclude (party_id),
            case party_id when 0 then null else party_id end as party_id
        from ({scored_query}) as scored
    """
    duck.compile(query_to_parquet(final_query, dest=combined_dest)).run()

    if update_from_hash:
        if compiled_policy_output.exists():
            merged_dest = compiled_dir / "policy_distributions_merged.parquet"
            person_filter = ",".join(str(int(x)) for x in person_ids or [])
            merge_query = f"""
                select row_number() over () as id, merged.* exclude (id)
                from (
                    select * from '{compiled_policy_output}'
                    where person_id not in ({person_filter})
                    union all by name
                    select * from '{combined_dest}'
                ) as merged
            """
            duck.compile(query_to_parquet(merge_query, dest=merged_dest)).run()
            merged_dest.replace(compiled_policy_output)
        else:
            combined_dest.replace(compiled_policy_output)
        combined_dest.unlink(missing_ok=True)
    else:
        combined_dest.replace(compiled_policy_output)

    count = duck.compile(
        f"select count(*) as count from '{compiled_policy_output}'"
    ).df()
    return int(count.iloc[0]["count"])


@import_register.register("policycalc", group=ImportOrder.POLICYCALC)
def run_policy_calculations(
    quiet: bool = False, update_since: datetime.date | None = None
) -> None:
    partial_update = update_since is not None

    sources = [
        policy_divisions_relevant,
        policy_agreements_relevant,
        policy_votes_relevant,
        policy_collective_relevant,
        pw_relevant_people,
    ]

    for s in sources:
        if s.source.exists() is False:
            raise ValueError(f"{s.source} not present")

    count = generate_policy_distributions(update_from_hash=partial_update, quiet=quiet)

    if not quiet:
        rich.print(f"Calculated [green]{count}[/green] policy distributions")

    joined_path = compiled_dir / "policy_calc_to_load.parquet"

    if count:
        count = VoteDistribution.replace_with_parquet(joined_path)

    if not quiet:
        rich.print(
            f"Created [green]{count}[/green] policy distributions in the database"
        )
