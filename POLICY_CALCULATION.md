# How the policy calculation works

This document explains, in ordinary language, how the project turns individual
votes and parliamentary agreements into a policy score for a person and a
comparison with their party.

The production query is assembled in
[`votes/populate/policycalc_query.py`](votes/populate/policycalc_query.py). It is
written as a sequence of named stages. Although those stages appear separately in
the Python source, the Duck adapter combines them into one DuckDB query before it
runs.

## The result we are trying to produce

For each relevant person, policy, and comparison period, the calculation produces
up to two rows:

- The **target row** describes how the person voted.
- The **comparison row** describes how the other members of the person's
  comparison party voted.

Each row records weighted and unweighted counts for:

- votes that agreed with the policy;
- votes that disagreed with the policy;
- absences;
- abstentions; and
- parliamentary agreements that agreed or disagreed with the policy.

Those counts are then converted into the final `distance_score`. A low score means
the voting record is close to the policy's agreeing position; a high score means
it is close to the disagreeing position.

## The calculation at a glance

```text
Relevant people and policies
            │
            ▼
Choose person/chamber/party targets
            │
            ▼
Find policy divisions during each person's membership
            │
            ├───────────────┐
            ▼               ▼
Count the person's vote   Count the party's votes once
            │               │
            └───────┬───────┘
                    ▼
          Summarize by policy and period
                    │
                    ├──── Add agreement counts
                    ▼
          Fill missing counts and score
                    │
                    ▼
       policy_calc_to_load.parquet and PostgreSQL
```

## Before the main query: prepare smaller input tables

[`prep_policycalc.py`](votes/populate/prep_policycalc.py) reduces the much larger
source tables to the decisions, votes, people, and memberships relevant to at
least one policy.

- [`policy_divisions_relevant`](votes/populate/prep_policycalc.py#L64) joins each
  policy's division links to division details and comparison periods.
- [`votes_relevant`](votes/populate/prep_policycalc.py#L91) keeps votes only for
  policy-linked divisions and converts vote positions into small numeric fields.
- [`policy_agreements_relevant`](votes/populate/prep_policycalc.py#L121) does the
  equivalent preparation for parliamentary agreements.
- [`collective_relevant`](votes/populate/prep_policycalc.py#L148) identifies the
  people who were members of the chamber when an agreement happened.
- [`relevant_people`](votes/populate/prep_policycalc.py#L234) creates the complete
  list of person, chamber, policy, period, and comparison-party relationships
  that should produce results.

The main calculation reads these prepared parquet files instead of repeatedly
joining the complete application tables.

## Step 1: choose the calculation targets

[`selected_targets`](votes/populate/policycalc_query.py#L84) produces one row for
each person, chamber, and comparison party that needs calculating.

A person without a comparison party temporarily uses party ID `0`. This sentinel
is converted back to `NULL` in the final output.

This is also the only stage where a partial calculation is filtered. For example,
the validator restricts it to one sampled person/chamber/party combination.

## Step 2: find the divisions the person was eligible for

[`eligible_divisions`](votes/populate/policycalc_query.py#L101) connects each
target to every policy-linked division that happened during one of their
memberships in the chamber.

The membership is deliberately not filtered by party. The party is the group used
for comparison; it does not determine the dates on which the person was eligible
to participate. This matters for people who changed party or had more than one
membership period.

At this point, one row means:

> One target person, one policy link, and one division.

## Step 3: count each party's votes once

[`party_division_votes`](votes/populate/policycalc_query.py#L130) groups the
prepared vote data by party and division. It records how many members voted aye,
voted no, abstained, or were absent.

This is the main performance optimization. Many people are compared with the same
party in the same division, so the party total is calculated once and reused
instead of scanning every party member again for every person.

At this point, one row means:

> One party's totals in one division.

## Step 4: produce target and party results for each division

The calculation now follows two branches.

[`target_by_division`](votes/populate/policycalc_query.py#L202) reads the person's
own vote and decides whether it agreed with the policy, disagreed, was an
abstention, or was an absence.

[`comparison_by_division`](votes/populate/policycalc_query.py#L151) uses the
reusable party totals. If the target person belonged to that party for a division,
their vote is subtracted from the party total. The comparison therefore means
“the other members of the party” and never counts the target in both rows.

For party comparisons, each division contributes fractions whose total is one.
For example, if 60 of 100 other party members agreed with the policy, that
division contributes `0.6` to `num_votes_same`. This prevents large parties from
having more influence merely because they have more members.

## Step 5: summarize divisions by policy and period

[`target_comparison`](votes/populate/policycalc_query.py#L235) and
[`party_comparison`](votes/populate/policycalc_query.py#L244) add together the
per-division results for each policy and comparison period.

They also retain two diagnostic lists:

- `division_ids` identifies the divisions included in the result;
- `num_comparators` records how many votes contributed to the corresponding
  division.

The two lists correspond by position, but their physical order is not meaningful.
Avoiding a sort for every result group is an important performance saving.

[`division_comparison`](votes/populate/policycalc_query.py#L253) then combines the
target and party branches. At this point, one row means:

> One person, chamber, party, policy, period, and result type.

The result type is `is_target = 1` for the person's row and `is_target = 0` for
the party comparison.

## Step 6: add parliamentary agreements

Not every policy decision is a recorded division. Some are parliamentary
agreements, where the project knows that the chamber agreed but has no individual
vote for each member.

[`agreement_comparison`](votes/populate/policycalc_query.py#L266) counts the
agreements that occurred while each person was a member of the chamber. Agreement
counts are the same for the target and party comparison, so they are calculated
once per person, policy, and period and reused.

[`result_keys`](votes/populate/policycalc_query.py#L297) makes sure that policies
containing only agreements still receive a target result even though they have no
division result.

## Step 7: normalize and score the result

[`scored_bulk_policy_query`](votes/populate/policycalc_query.py#L358) adds a short
second sequence of stages:

- [`results`](votes/populate/policycalc_query.py#L367) represents the complete
  unscored output row.
- [`normalized`](votes/populate/policycalc_query.py#L380) converts missing numeric
  counts to zero. Diagnostic lists are allowed to remain null.
- [`score_inputs`](votes/populate/policycalc_query.py#L394) applies the strong-vote
  and abstention weights.
- [`initial_score`](votes/populate/policycalc_query.py#L417) calculates the raw
  distance score.
- [`absence_capped_score`](votes/populate/policycalc_query.py#L432) prevents a
  record with substantial absences from receiving misleadingly absolute language.

The comparison at the one-third absence boundary is rounded to 12 decimal places.
This does not round the vote totals or ordinary scores. It only stops parallel
floating-point addition from placing a mathematically exact boundary just above
or below the cap by an infinitesimal amount.

## Step 8: save and load the result

[`generate_policy_distributions`](votes/populate/policycalc.py#L210) asks DuckDB to
run the composed query and writes the result atomically to
`data/compiled/policy_calc_to_load.parquet`.

[`run_policy_calculations`](votes/populate/policycalc.py#L277) then replaces the
`VoteDistribution` database table from that parquet. The generic loader is
implemented by [`sync_to_postgres`](twfy_votes/helpers/duck/postgres_link.py),
which reorders the parquet columns to match the database table before replacing
its contents.

## How the named stages become one query

The `@pipeline.as_cte(...)` decorator is implemented in
[`DuckQuery.as_cte`](twfy_votes/helpers/duck/core.py#L120). It records the stage's
name, SQL, dependencies, and materialization choice.

[`DuckQuery.render_ctes`](twfy_votes/helpers/duck/core.py#L166) renders all those
stages into one `WITH` statement. This means the named Python classes improve
readability without turning the calculation into many separately executed
queries.

Stages marked `MATERIALIZED` are expensive results that are reused or deliberately
kept as an intermediate boundary. Stages marked `NOT MATERIALIZED` are single-use
transformations that DuckDB can inline into the surrounding query.

## How correctness is checked

[`vr_validator.py`](votes/management/commands/vr_validator.py) contains a slow,
straightforward Python/ORM implementation intended to be easy to inspect.

[`validate_approach`](votes/management/commands/vr_validator.py#L414) compares that
independent implementation with the live bulk query. It restricts
`bulk_policy_pivot_query()` to the sampled target, then compares the resulting
target and party counts with the slow calculation.

This is intentionally different from maintaining a second “fast” SQL query: the
validator always exercises the same query that production uses.
