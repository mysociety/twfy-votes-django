"""
This module contains the sequence of macros to
generate a voting record for a person.
"""

import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich
from tqdm import tqdm

from twfy_votes.helpers.duck import DuckQuery
from twfy_votes.helpers.duck.funcs import query_to_parquet
from twfy_votes.helpers.duck.templates import EnforceIntJinjaQuery
from votes.models.decisions import Policy, VoteDistribution
from votes.policy_generation.scoring import ScoreFloatPair

from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")
compiled_policy_dir = Path(compiled_dir, "policies")


@duck.as_table
class policy_divisions_relevant:
    source = compiled_dir / "policy_divisions_relevant.parquet"


@duck.as_table
class policy_agreements_relevant:
    source = compiled_dir / "policy_agreements_relevant.parquet"


@duck.as_table
class policy_votes_relevant:
    source = compiled_dir / "policy_votes_relevant.parquet"


@duck.as_query
class make_indexes:
    query = """
    CREATE INDEX division_id ON policy_divisions_relevant (id);
    CREATE INDEX votes_division ON policy_votes_relevant (division_id);
    CREATE INDEX votes_person ON policy_votes_relevant (person_id);
    """


@duck.as_table
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


@duck.as_table_macro
class target_memberships:
    """
    Table macro to get the memberships for a person in a chamber
    """

    args = ["_person_id", "_chamber_id"]
    macro = """
    select
        *
    from
        pd_memberships
    where
        person_id = {{ _person_id }} and
        chamber_id = {{ _chamber_id }}
    """


@duck.as_table_macro
class agreement_count:
    """
    We want to know, by person_id, how many agreements they were in parliament for by policy.
    By *definition* this is the same for both target and non_target, so can be merged in the last step.
    """

    args = ["_person_id"]
    macro = """
    select
        period_id,
        person_id,
        policy_id,
        -- count agreement where strength is strong and alignment is agree
        count(*) filter (where strong_int = 1 and agree_int = 1) as num_strong_agreements_same,
        -- count agreement where strength is weak and alignment is agree
        count(*) filter (where strong_int = 0 and agree_int = 1) as num_agreements_same,
        -- count agreement where strength is strong and alignment is disagree
        count(*) filter (where strong_int = 1 and agree_int = 0) as num_strong_agreements_different,
        -- count agreement where strength is weak and alignment is disagree
        count(*) filter (where strong_int = 0 and agree_int = 0) as num_agreements_different
    from
        policy_collective_relevant
    join
        policy_agreements_relevant
         on (policy_collective_relevant.decision_id = policy_agreements_relevant.id)
    where
        policy_collective_relevant.person_id = {{ _person_id }}
    group by
        all
    """


@duck.as_table_macro
class policy_alignment:
    """
    Table macro - For each vote/absence, calculate the policy alignment per person.
    """

    args = ["_person_id", "_chamber_id", "_party_id"]
    macro = """
    SELECT
        period_id,
        policy_id,
        pw_vote.person_id as person_id,
        case pw_vote.person_id when {{ _person_id }} then 1 else 0 end as is_target,
        strong_int,
        policy_divisions.id as division_id,
        policy_divisions.date as division_date,
        policy_divisions.division_number as division_number,
        policy_divisions.division_year as division_year,
        pw_vote.effective_vote as mp_vote,
        -- ok, effective_vote_int should be 1 for agree, -1 for disagree
        -- agree_int is 1 for 'policy agrees with vote', 0 for 'policy disagrees with vote'
        -- so aligned with policy is (1,1) or (-1,0) and not aligned is (1,0) or (-1,1)
        (case when pw_vote.effective_vote_int = 1 and agree_int = 1 
                or pw_vote.effective_vote_int = -1 and agree_int = 0 then 1 else 0 end) as answer_agreed,
        (case when pw_vote.effective_vote_int = 1 and agree_int = 0 
                or pw_vote.effective_vote_int = -1 and agree_int = 1 then 1 else 0 end) as answer_disagreed,
        pw_vote.abstain_int as abstained,
        pw_vote.absent_int as absent,
    FROM
        -- this is the divisions table merged with the division_links table and the period table
        policy_divisions_relevant as policy_divisions
    join
        -- limit to divisions within the memberships of our target person
        target_memberships({{ _person_id}}, {{ _chamber_id }}) as target_memberships
            on policy_divisions.date between target_memberships.start_date and target_memberships.end_date
    join
        -- now we bring in the actual votes
        -- this has already been reduced to only votes for divisions we care about
        policy_votes_relevant as pw_vote on (policy_divisions.id = pw_vote.division_id)
    where
        policy_divisions.chamber_id = {{ _chamber_id }}
        and ( -- here we want either the persons own divisions, or the divisions of the party they are in.
            pw_vote.person_id = {{ _person_id }}
            or
            pw_vote.effective_party_id = {{ _party_id }}
            )
    """


@duck.as_table_macro
class comparisons_by_policy_vote:
    """
    Table Macro.
    For each policy/vote, group up both the target and the comparison mps, and create an equiv score for the comparison
    This will be floats - but will sum to the same total of votes as the number of divisions the target could vote in.
    """

    args = ["_person_id", "_chamber_id", "_party_id"]
    macro = """
    select
        period_id,
        is_target,
        policy_id,
        division_id,
        ANY_VALUE(strong_int) as strong_int,
        count(*) as total,
        any_value(division_year) as division_year,
        sum(answer_agreed) / total as num_divisions_agreed,
        sum(answer_disagreed) / total as num_divisions_disagreed,
        sum(abstained) / total as num_divisions_abstain,
        sum(absent) / total as num_divisions_absent,
        sum(answer_agreed) + sum(answer_disagreed) + sum(abstained) + sum(absent) as num_comparators,
    from
        policy_alignment({{ _person_id }},
                         {{ _chamber_id }},
                         {{ _party_id }})
    group by
        period_id, is_target, policy_id, division_id
    """


@duck.as_table_macro
class comparisons_by_policy_vote_pivot:
    args = ["_person_id", "_chamber_id", "_party_slug"]
    macro = """
    select
        period_id,
        is_target,
        policy_id,
        sum(num_divisions_agreed) filter (where strong_int = 0) as num_votes_same,
        sum(num_divisions_agreed) filter (where strong_int = 1) as num_strong_votes_same,
        sum(num_divisions_disagreed) filter (where strong_int = 0) as num_votes_different,
        sum(num_divisions_disagreed) filter (where strong_int = 1) as num_strong_votes_different,
        sum(num_divisions_absent) filter (where strong_int = 0) as num_votes_absent,
        sum(num_divisions_absent) filter (where strong_int = 1) as num_strong_votes_absent,
        sum(num_divisions_abstain) filter (where strong_int = 0) as num_votes_abstain,
        sum(num_divisions_abstain) filter (where strong_int = 1) as num_strong_votes_abstain,
        list(num_comparators) as num_comparators,
        -- for debugging - remove for speed
        list(division_id) as division_ids,
        min(division_year) as start_year,
        max(division_year) as end_year
    from comparisons_by_policy_vote({{ _person_id }},
                                    {{ _chamber_id }},
                                    {{ _party_slug }}
                                    )
    group by
        period_id, is_target, policy_id
    """


@duck.as_table_macro
class joined_division_agreement_comparison:
    """
    Bring the division and agreement calculations together.
    By definition, agreements don't differ, so there is no is_target to merge on
    """

    args = ["_person_id", "_chamber_id", "_party_slug"]
    macro = """
    select
        coalesce(division_comparison.period_id, agreement_comparison.period_id) as period_id,
        coalesce(division_comparison.policy_id, agreement_comparison.policy_id) as policy_id,
        coalesce(division_comparison.is_target, 0) as is_target,
        {{ _person_id }} as person_id,
        {{ _chamber_id }} as chamber_id,
        {{ _party_slug }} as party_id,
        division_comparison.* exclude (period_id, policy_id, is_target),
        agreement_comparison.* exclude (period_id, policy_id)
    from
        comparisons_by_policy_vote_pivot({{ _person_id }},
                                        {{ _chamber_id }},
                                        {{ _party_slug }}
                                        ) as division_comparison
    full join
        agreement_count({{ _person_id }}) as agreement_comparison using (policy_id, period_id)
    """


@duck.as_query
class prepared_pivot_table:
    query = """
    PREPARE prepared_pivot_table AS
    select * from joined_division_agreement_comparison($person_id, $chamber_id, $party_id)
    """


# so if we load before any files exist it's ok to create
if any(compiled_policy_dir.glob("*.parquet")):

    @duck.as_source
    class compiled_policies:  # type: ignore
        source = compiled_policy_dir / "*.parquet"

else:
    # create an equiv empty table with these
    # columns person_id, period_id, policy_id, party_id, policy_hash

    @duck.as_view
    class compiled_policies:
        query = """
        select
            null as person_id,
            null as period_id,
            null as policy_id,
            null as party_id,
            null as policy_hash
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
        id as policy_id,
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
        coalesce(party_id, 0) as party_id,
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
        rp.person_id as person_id,
        rp.chamber_id as chamber_id,
        rp.period_id as period_id,
        rp.policy_id as policy_id,
        rp.party_id as party_id,
        rp.policy_hash as current_hash,
        compiled_policies.policy_hash as compiled_hash,
        current_hash != compiled_hash as hash_differs
    from 
        relevant_person_policy_period_with_hash as rp
    left join
        compiled_policies using (person_id, period_id, policy_id, party_id)
        
    """


class PolicyPivotTable(EnforceIntJinjaQuery):
    """
    Retrieve all policy breakdowns and comparison breakdowns
    for a single person, given a chamber and a party.
    """

    query_template = """
    EXECUTE prepared_pivot_table(person_id := {{ person_id }},
                                 chamber_id := {{ chamber_id }},
                                 party_id := {{ party_id }})
    """
    person_id: int
    chamber_id: int
    party_id: int


def get_connected_duck():
    connected = DuckQuery.connect()
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


def score_generation_func():
    """
    This in principle can be replaced by a vectorised approach.
    The problem is this is at the moment applied at the person level.
    The scoring approach is done at the policy level.
    *in principle* different policies can have different scoring functions.
    So it needs to be all bought together in total, split by policy, and then have scoring calculated.
    There will be time saving associated with this, but seconds rather than minutes.
    """
    policies = Policy.objects.all()
    policy_score_func = {x.id: x.get_scoring_function() for x in policies}

    def get_score(row: pd.Series) -> float:
        scoring_func = policy_score_func[row["policy_id"]]
        return scoring_func.score(
            votes_same=ScoreFloatPair(
                row["num_votes_same"], row["num_strong_votes_same"]
            ),
            votes_different=ScoreFloatPair(
                row["num_votes_different"], row["num_strong_votes_different"]
            ),
            votes_absent=ScoreFloatPair(
                row["num_votes_absent"], row["num_strong_votes_absent"]
            ),
            votes_abstain=ScoreFloatPair(
                row["num_votes_abstain"], row["num_strong_votes_abstain"]
            ),
            agreements_same=ScoreFloatPair(
                row["num_agreements_same"], row["num_strong_agreements_same"]
            ),
            agreements_different=ScoreFloatPair(
                row["num_agreements_different"],
                row["num_strong_agreements_different"],
            ),
        )

    return get_score


def generate_combo_with_id(source: Path, dest: Path):
    """
    Create a parquet file with all the items for copying into the database
    """
    duck = get_connected_duck()
    query = f"""
    select
        row_number() over() as id,
        compiled_policies.* exclude (party_id),
        case party_id when 0 then null else party_id end as party_id
    from '{source}' as compiled_policies
    """

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
    score_from_row = score_generation_func()

    policy_hash_df = duck.get_view(policy_hash).df()
    policy_id_lookup = policy_hash_df.set_index(["policy_id"])["policy_hash"].to_dict()

    policy_dest = compiled_dir / "policies"
    if not update_from_hash:
        if policy_dest.exists():
            for file in policy_dest.glob("*"):
                file.unlink()
            policy_dest.rmdir()

    policy_dest.mkdir(exist_ok=True, parents=True)

    relevant_df = pd.read_parquet(
        compiled_dir / "relevant_person_policy_period.parquet"
    )

    if person_ids:
        relevant_df = relevant_df[relevant_df["person_id"].isin(person_ids)]

    else:
        if update_from_hash:
            person_ids = check_generated_against_current()
            relevant_df = relevant_df[relevant_df["person_id"].isin(person_ids)]

    if policy_ids:
        # Note, this will still regenerate other policies, just exclude people who *don't* have this policy
        relevant_df = relevant_df[relevant_df["policy_id"].isin(policy_ids)]
    relevant_df = relevant_df.drop(
        columns=["policy_id", "period_id", "effective_party_slug"]
    ).drop_duplicates()

    # for true independents who never had a party - setting to 0 means there is no comparison party to find
    relevant_df["party_id"] = relevant_df["party_id"].fillna(0).astype(int)
    relevant_df["chamber_id"] = relevant_df["chamber_id"].astype(int)
    relevant_df["person_id"] = relevant_df["person_id"].astype(int)

    count = 0

    for _, row in tqdm(relevant_df.iterrows(), total=len(relevant_df), disable=quiet):
        df = (
            PolicyPivotTable(
                person_id=row["person_id"],
                chamber_id=row["chamber_id"],
                party_id=row["party_id"],
            )
            .compile(duck)
            .df()
        )

        list_cols = ["num_comparators", "division_ids"]
        for col in df.columns:
            if col not in list_cols:
                df[col] = df[col].fillna(0)

        df["policy_hash"] = df["policy_id"].map(policy_id_lookup)
        distances = df.apply(score_from_row, axis=1)
        try:
            df["distance_score"] = distances
        except Exception as e:
            print(distances)
            raise e

        df.to_parquet(
            policy_dest
            / f"{row['person_id']}_{row['chamber_id']}_{row['party_id']}.parquet"
        )
        count += len(df)

    return count


@import_register.register("policycalc", group=ImportOrder.POLICYCALC)
def run_policy_calculations(
    quiet: bool = False, update_since: datetime.date | None = None
):
    partial_update = update_since is not None

    count = generate_policy_distributions(update_from_hash=partial_update, quiet=quiet)

    if not quiet:
        rich.print(f"Calculated [green]{count}[/green] policy distributions")

    source_path = compiled_policy_dir / "*.parquet"
    joined_path = compiled_dir / "policy_calc_to_load.parquet"

    generate_combo_with_id(source_path, joined_path)

    if count:
        with VoteDistribution.disable_constraints():
            count = VoteDistribution.replace_with_parquet(joined_path)

    if not quiet:
        rich.print(
            f"Created [green]{count}[/green] policy distributions in the database"
        )
