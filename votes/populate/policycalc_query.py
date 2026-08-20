"""Set-based DuckDB query used by the production policy calculation.

Each class below is one named CTE stage.  Class docstrings describe the stage's
row grain: the set of columns that uniquely identifies what one row represents.
Keeping those grains explicit makes the two important fan-outs in this query
(targets to divisions, and divisions to party votes) much easier to reason about.

Materialization is intentional.  Large stages referenced more than once are
materialized; single-use transformations remain inline so DuckDB can optimize
through them.  ``DuckQuery.render_ctes`` still emits one SQL statement.
"""

from __future__ import annotations

from typing import NamedTuple

from twfy_votes.helpers.duck import DuckQuery


class PolicyCountPipeline(NamedTuple):
    """
    Named components needed to render the policy-count query.
    """

    pipeline: DuckQuery
    result_query: str


COMPARISON_AGGREGATION = """
select
    person_id,
    chamber_id,
    party_id,
    period_id,
    policy_id,
    is_target,
    sum(agreed::double / total) filter (where strong_int = 0) as num_votes_same,
    sum(agreed::double / total) filter (where strong_int = 1) as num_strong_votes_same,
    sum(disagreed::double / total) filter (where strong_int = 0) as num_votes_different,
    sum(disagreed::double / total) filter (where strong_int = 1) as num_strong_votes_different,
    sum(absent::double / total) filter (where strong_int = 0) as num_votes_absent,
    sum(absent::double / total) filter (where strong_int = 1) as num_strong_votes_absent,
    sum(abstained::double / total) filter (where strong_int = 0) as num_votes_abstain,
    sum(abstained::double / total) filter (where strong_int = 1) as num_strong_votes_abstain,
    -- These lists are diagnostic output. Their values correspond by position,
    -- but their physical order is deliberately unspecified to avoid a sort in
    -- every group.
    list((agreed + disagreed + abstained + absent)::double) as num_comparators,
    list(division_id) as division_ids,
    min(division_year) as start_year,
    max(division_year) as end_year
from {source}
group by person_id, chamber_id, party_id, period_id, policy_id, is_target
"""


NUMERIC_RESULT_COLUMNS = [
    "start_year",
    "end_year",
    "num_votes_same",
    "num_strong_votes_same",
    "num_votes_different",
    "num_strong_votes_different",
    "num_votes_absent",
    "num_strong_votes_absent",
    "num_votes_abstain",
    "num_strong_votes_abstain",
    "person_id_1",
    "num_strong_agreements_same",
    "num_agreements_same",
    "num_strong_agreements_different",
    "num_agreements_different",
]


def policy_count_pipeline(target_filter: str = "") -> PolicyCountPipeline:
    """
    Build the named stages that calculate vote and agreement counts.
    """

    pipeline = DuckQuery()

    @pipeline.as_cte(materialized=True)
    class selected_targets:
        """Grain: person, chamber, comparison party.

        This is the only stage containing dynamic filters. A null party becomes
        the internal ``0`` sentinel used for people without a comparator party.
        """

        query = f"""
        select distinct
            person_id,
            chamber_id::integer as chamber_id,
            coalesce(party_id, 0)::integer as party_id
        from relevant_person_policy_period
        {target_filter}
        """

    @pipeline.as_cte(materialized=True)
    class eligible_divisions:
        """Grain: target and policy-linked division.

        A target is eligible for a division when it occurred during any of their
        memberships in the chamber. Membership is deliberately not restricted by
        party: a target can be compared with a historical party across multiple
        membership periods.
        """

        depends_on = [selected_targets]
        query = """
        select
            targets.person_id,
            targets.chamber_id,
            targets.party_id,
            divisions.period_id,
            divisions.policy_id,
            divisions.id as division_id,
            divisions.division_year,
            divisions.strong_int,
            divisions.agree_int
        from selected_targets as targets
        join pd_memberships as memberships using (person_id, chamber_id)
        join policy_divisions_relevant as divisions
          on divisions.chamber_id = targets.chamber_id
         and divisions.date between memberships.start_date and memberships.end_date
        """

    @pipeline.as_cte(materialized=True)
    class party_division_votes:
        """Grain: party and division.

        This is the main reusable cache. Party vote totals are calculated once,
        rather than scanning all party members again for every target.
        """

        query = """
        select
            division_id,
            effective_party_id as party_id,
            count(*) as total,
            count(*) filter (where effective_vote_int = 1) as ayes,
            count(*) filter (where effective_vote_int = -1) as noes,
            sum(abstain_int) as abstains,
            sum(absent_int) as absences
        from policy_votes_relevant
        group by division_id, effective_party_id
        """

    @pipeline.as_cte(materialized=False)
    class comparison_by_division:
        """Grain: target and policy-linked division; comparator result only.

        The target's own vote is subtracted when they belong to the comparison
        party. This reproduces the old ``target OR party`` join without counting
        the target in both result groups.
        """

        depends_on = [eligible_divisions, party_division_votes]
        query = """
        select
            eligible.person_id,
            eligible.chamber_id,
            eligible.party_id,
            eligible.period_id,
            eligible.policy_id,
            0 as is_target,
            eligible.division_id,
            eligible.division_year,
            eligible.strong_int,
            party_votes.total
              - case when target.effective_party_id = eligible.party_id then 1 else 0 end
              as total,
            case when eligible.agree_int = 1 then party_votes.ayes else party_votes.noes end
              - case when target.effective_party_id = eligible.party_id
                           and ((eligible.agree_int = 1 and target.effective_vote_int = 1)
                             or (eligible.agree_int = 0 and target.effective_vote_int = -1))
                       then 1 else 0 end as agreed,
            case when eligible.agree_int = 1 then party_votes.noes else party_votes.ayes end
              - case when target.effective_party_id = eligible.party_id
                           and ((eligible.agree_int = 1 and target.effective_vote_int = -1)
                             or (eligible.agree_int = 0 and target.effective_vote_int = 1))
                       then 1 else 0 end as disagreed,
            party_votes.abstains
              - case when target.effective_party_id = eligible.party_id
                     then target.abstain_int else 0 end as abstained,
            party_votes.absences
              - case when target.effective_party_id = eligible.party_id
                     then target.absent_int else 0 end as absent
        from eligible_divisions as eligible
        join party_division_votes as party_votes
          on party_votes.division_id = eligible.division_id
         and party_votes.party_id = eligible.party_id
        left join policy_votes_relevant as target
          on target.person_id = eligible.person_id
         and target.division_id = eligible.division_id
        where party_votes.total
              - case when target.effective_party_id = eligible.party_id then 1 else 0 end > 0
        """

    @pipeline.as_cte(materialized=False)
    class target_by_division:
        """
        Grain: target and policy-linked division; target result only.
        """

        depends_on = [eligible_divisions]
        query = """
        select
            eligible.person_id,
            eligible.chamber_id,
            eligible.party_id,
            eligible.period_id,
            eligible.policy_id,
            1 as is_target,
            eligible.division_id,
            eligible.division_year,
            eligible.strong_int,
            1 as total,
            case when (votes.effective_vote_int = 1 and eligible.agree_int = 1)
                       or (votes.effective_vote_int = -1 and eligible.agree_int = 0)
                 then 1 else 0 end as agreed,
            case when (votes.effective_vote_int = 1 and eligible.agree_int = 0)
                       or (votes.effective_vote_int = -1 and eligible.agree_int = 1)
                 then 1 else 0 end as disagreed,
            votes.abstain_int as abstained,
            votes.absent_int as absent
        from eligible_divisions as eligible
        join policy_votes_relevant as votes
          on votes.division_id = eligible.division_id
         and votes.person_id = eligible.person_id
        """

    @pipeline.as_cte(materialized=True)
    class target_comparison:
        """
        Grain: target, policy, period, and ``is_target = 1``.
        """

        depends_on = [target_by_division]
        query = COMPARISON_AGGREGATION.format(source="target_by_division")

    @pipeline.as_cte(materialized=True)
    class party_comparison:
        """
        Grain: target, policy, period, and ``is_target = 0``.
        """

        depends_on = [comparison_by_division]
        query = COMPARISON_AGGREGATION.format(source="comparison_by_division")

    @pipeline.as_cte(materialized=True)
    class division_comparison:
        """
        Grain: target, policy, period, and target/comparator result type.
        """

        depends_on = [target_comparison, party_comparison]
        query = """
        select * from target_comparison
        union all
        select * from party_comparison
        """

    @pipeline.as_cte(materialized=True)
    class agreement_comparison:
        """Grain: person, policy, and period.

        Agreements have no distinct party-comparator result, so these counts are
        calculated once per person and later attached to both division results.
        """

        depends_on = [selected_targets]
        query = """
        select
            collective.person_id,
            agreements.period_id,
            agreements.policy_id,
            count(*) filter (where strong_int = 1 and agree_int = 1)
                as num_strong_agreements_same,
            count(*) filter (where strong_int = 0 and agree_int = 1)
                as num_agreements_same,
            count(*) filter (where strong_int = 1 and agree_int = 0)
                as num_strong_agreements_different,
            count(*) filter (where strong_int = 0 and agree_int = 0)
                as num_agreements_different,
            min(date_part('year', agreements.date)) as agreement_start_year,
            max(date_part('year', agreements.date)) as agreement_end_year
        from policy_collective_relevant as collective
        join policy_agreements_relevant as agreements
          on collective.decision_id = agreements.id
        where collective.person_id in (select person_id from selected_targets)
        group by collective.person_id, agreements.period_id, agreements.policy_id
        """

    @pipeline.as_cte(materialized=True)
    class result_keys:
        """Grain: every key that must appear in the final output.

        The union adds agreement-only policies, which have a target result but no
        division result.
        """

        depends_on = [division_comparison, selected_targets, agreement_comparison]
        query = """
        select person_id, chamber_id, party_id, period_id, policy_id, is_target
        from division_comparison
        union
        select targets.person_id, targets.chamber_id, targets.party_id,
               agreements.period_id, agreements.policy_id, 1 as is_target
        from selected_targets as targets
        join agreement_comparison as agreements using (person_id)
        """

    result_query = """
    select
        keys.period_id,
        keys.policy_id,
        keys.is_target,
        keys.person_id,
        keys.chamber_id,
        least(divisions.start_year, agreements.agreement_start_year) as start_year,
        greatest(divisions.end_year, agreements.agreement_end_year) as end_year,
        divisions.num_votes_same,
        divisions.num_strong_votes_same,
        divisions.num_votes_different,
        divisions.num_strong_votes_different,
        divisions.num_votes_absent,
        divisions.num_strong_votes_absent,
        divisions.num_votes_abstain,
        divisions.num_strong_votes_abstain,
        divisions.num_comparators,
        divisions.division_ids,
        agreements.person_id as person_id_1,
        agreements.num_strong_agreements_same,
        agreements.num_agreements_same,
        agreements.num_strong_agreements_different,
        agreements.num_agreements_different,
        keys.party_id
    from result_keys as keys
    left join division_comparison as divisions
      using (person_id, chamber_id, party_id, period_id, policy_id, is_target)
    left join agreement_comparison as agreements
      using (person_id, period_id, policy_id)
    """
    return PolicyCountPipeline(pipeline=pipeline, result_query=result_query)


def bulk_policy_pivot_query(target_filter: str = "") -> str:
    """
    Render the unscored bulk result, primarily for validation and debugging.
    """

    count_pipeline = policy_count_pipeline(target_filter)
    return count_pipeline.pipeline.render_ctes(count_pipeline.result_query)


def scored_bulk_policy_query(target_filter: str = "") -> str:
    """
    Render counts, normalization, hashes, and scoring as one statement.
    """

    count_pipeline = policy_count_pipeline(target_filter)
    pipeline = count_pipeline.pipeline

    @pipeline.as_cte(materialized=True)
    class results:
        """
        Grain: one complete unscored policy-distribution output row.
        """

        query = count_pipeline.result_query

    normalized_columns = ",\n".join(
        f"coalesce(results.{column}, 0) as {column}"
        for column in NUMERIC_RESULT_COLUMNS
    )

    @pipeline.as_cte(materialized=True)
    class normalized:
        """
        Grain: one result row, with numeric nulls converted to zero.
        """

        depends_on = [results]
        query = f"""
        select
            results.* exclude ({', '.join(NUMERIC_RESULT_COLUMNS)}),
            {normalized_columns}
        from results
        """

    @pipeline.as_cte(materialized=False)
    class score_inputs:
        """
        Grain: one result row plus weighted scoring intermediates.
        """

        depends_on = [normalized]
        query = """
        select
            normalized.*,
            10.0 * (num_strong_votes_different + num_strong_agreements_different)
                + 5.0 * num_strong_votes_abstain as score_points,
            10.0 * (
                num_strong_votes_same + num_strong_votes_different
                + num_strong_agreements_same + num_strong_agreements_different
                + num_strong_votes_abstain
            ) as available_points,
            num_strong_votes_same + num_strong_votes_different
                + num_strong_votes_absent + num_strong_votes_abstain
                as strong_vote_total
        from normalized
        """

    @pipeline.as_cte(materialized=False)
    class initial_score:
        """
        Grain: one result row plus its uncapped distance score.
        """

        depends_on = [score_inputs]
        query = """
        select
            score_inputs.*,
            case when available_points = 0 then -1.0
                 else score_points / available_points end as uncapped_score
        from score_inputs
        """

    @pipeline.as_cte(materialized=False)
    class absence_capped_score:
        """
        Grain: one result row after the first absence-cap rule.
        """

        depends_on = [initial_score]
        query = """
        select
            initial_score.*,
            case
                when num_strong_votes_absent > 1 and uncapped_score <= 0.05 then 0.06
                when num_strong_votes_absent > 1 and uncapped_score >= 0.95 then 0.94
                else uncapped_score
            end as once_capped_score
        from initial_score
        """

    final_query = """
    select
        absence_capped_score.* exclude (
            score_points, available_points, strong_vote_total, uncapped_score,
            once_capped_score, party_id
        ),
        policy_hash.policy_hash,
        case
            when available_points = 0 then -1.0
            -- Round only at the discontinuous threshold. Different parallel sum
            -- orders otherwise move exact thirds infinitesimally across the cap.
            when num_strong_votes_absent > 0
                 and round(num_strong_votes_absent, 12)
                     >= round(strong_vote_total / 3.0, 12)
                 and round(once_capped_score, 12) <= 0.15 then 0.16
            when num_strong_votes_absent > 0
                 and round(num_strong_votes_absent, 12)
                     >= round(strong_vote_total / 3.0, 12)
                 and round(once_capped_score, 12) >= 0.85 then 0.84
            else once_capped_score
        end as distance_score,
        absence_capped_score.party_id
    from absence_capped_score
    join policy_hash using (policy_id)
    """
    return pipeline.render_ctes(final_query)
