"""
This module contains the 'slow' approach to calculating the policies.
It is used to validate the 'fast' approach in vr_generator.py.
"""

import datetime
from math import isclose
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q

import pandas as pd
import rich
from pydantic import BaseModel, Field, computed_field
from tqdm import tqdm
from typing_extensions import Self

from ...consts import PolicyDirection, PolicyStrength, VotePosition
from ...models import (
    Chamber,
    Membership,
    Organization,
    Person,
    Policy,
    PolicyComparisonPeriod,
)
from ...populate.policycalc import PolicyPivotTable, get_connected_duck


class Score(BaseModel):
    num_votes_same: float = 0.0
    num_strong_votes_same: float = 0.0
    num_votes_different: float = 0.0
    num_strong_votes_different: float = 0.0
    num_votes_absent: float = 0.0
    num_strong_votes_absent: float = 0.0
    num_votes_abstain: float = 0.0
    num_strong_votes_abstain: float = 0.0
    num_agreements_same: float = 0.0
    num_strong_agreements_same: float = 0.0
    num_agreements_different: float = 0.0
    num_strong_agreements_different: float = 0.0
    num_comparators: list[int] = Field(default_factory=list)

    def __eq__(self, other: Self) -> bool:
        return not self.tol_errors(other)

    def tol_errors(self, other: Self) -> list[str]:
        """
        Allow 0.05 tolerance for floating point errors.
        """
        errors: list[str] = []

        def tol(a: float, b: float) -> bool:
            return isclose(a, b, abs_tol=0.05)

        fields = [
            "num_votes_same",
            "num_strong_votes_same",
            "num_votes_different",
            "num_strong_votes_different",
            "num_votes_absent",
            "num_strong_votes_absent",
            "num_votes_abstain",
            "num_strong_votes_abstain",
        ]

        for field in fields:
            if not tol((o := getattr(self, field)), (t := getattr(other, field))):
                errors.append(f"{field} is not equal - {o} != {t}")

        return errors

    @computed_field
    @property
    def total_votes(self) -> float:
        return (
            self.num_votes_same
            + self.num_votes_different
            + self.num_votes_absent
            + self.num_strong_votes_same
            + self.num_strong_votes_different
            + self.num_strong_votes_absent
            + self.num_votes_abstain
            + self.num_strong_votes_abstain
        )

    def reduce(self):
        """
        reduce each count to a fraction of the total vote.
        The new total should be 1.
        """
        new = self.model_copy()
        total = new.total_votes
        new.num_votes_same /= total
        new.num_votes_different /= total
        new.num_votes_absent /= total
        new.num_strong_votes_same /= total
        new.num_strong_votes_different /= total
        new.num_strong_votes_absent /= total
        new.num_votes_abstain /= total
        new.num_strong_votes_abstain /= total
        if not isclose(new.total_votes, 1.0):
            raise ValueError(f"Total votes should be 1, not {self.total_votes}")
        return new

    def __add__(self: Self, other: Self) -> Self:
        if isinstance(other, Score):
            self.num_votes_same += other.num_votes_same
            self.num_strong_votes_same += other.num_strong_votes_same
            self.num_votes_different += other.num_votes_different
            self.num_strong_votes_different += other.num_strong_votes_different
            self.num_votes_absent += other.num_votes_absent
            self.num_strong_votes_absent += other.num_strong_votes_absent
            self.num_votes_abstain += other.num_votes_abstain
            self.num_strong_votes_abstain += other.num_strong_votes_abstain
        else:
            raise TypeError(f"Cannot add {type(self)} and {type(other)}")
        return self


class PolicyComparison(BaseModel):
    target_distribution: Score
    other_distribution: Score

    def __eq__(self, other: Self) -> bool:
        target_eq = self.target_distribution == other.target_distribution
        other_eq = self.other_distribution == other.other_distribution

        return target_eq and other_eq


def get_party_members(party_slug: str):
    duck = get_connected_duck()

    query = """
                select * from pd_memberships
                where chamber = 'commons'
                and effective_party_slug = {{ party }}
                order by start_date asc
    """

    df = duck.compile(query, {"party": party_slug}).df()
    df["end_date"] = df["end_date"].fillna("9999-12-31")
    return df


def get_party_members_or_person(party_slug: str, person_id: int):
    duck = get_connected_duck()

    query = """
        select * from pd_memberships
        where chamber = 'commons'
        and (
            effective_party_slug = {{ party }}
        or
            person_id = {{ person_id }}
            )
        order by start_date asc
    """

    df = duck.compile(query, {"party": party_slug, "person_id": person_id}).df()
    df["end_date"] = df["end_date"].fillna("9999-12-31")
    return df


def get_mp_dates(person_id: int):
    duck = get_connected_duck()

    query = """
    select 
        person_id,
        start_date,
        end_date,
        from pd_memberships
        where chamber = 'commons'
        and person_id = {{ person_id }}
    order by start_date asc
    """

    df = duck.compile(query, {"person_id": person_id}).df()
    df["end_date"] = df["end_date"].fillna("9999-12-31")
    return df


def get_scores_slow(
    *,
    person_id: int,
    policy_id: int,
    party_id: int | None,
    period_id: int,
    chamber_id: int,
    debug: bool = False,
) -> PolicyComparison:
    """
    This calculates the score a much slower way than the SQL method.
    Wherever possible this has chosen a different approach to getting
    information and processing it.
    Ideally, this will agree with the less easy to read SQL method.
    """
    comparsion_period = PolicyComparisonPeriod.objects.get(id=period_id)
    policy = Policy.objects.get(id=policy_id)
    party = Organization.objects.get(id=party_id) if party_id else None
    person = Person.objects.get(id=person_id)
    chamber = Chamber.objects.get(id=chamber_id)

    member_score = Score()
    other_score = Score()

    def debug_print(*args: Any, **kwargs: Any):
        if debug:
            print(*args, **kwargs)

    # party member OR our person
    party_members = Membership.objects.filter(chamber=chamber).filter(
        Q(effective_party=party) | Q(person=person)
    )
    party_members = pd.DataFrame(
        party_members.values("person_id", "start_date", "end_date")
    )

    mp_dates = Membership.objects.filter(person=person, chamber=chamber)
    mp_dates = pd.DataFrame(mp_dates.values("person_id", "start_date", "end_date"))

    def is_valid_date(date: datetime.date) -> bool:
        mask = (mp_dates["start_date"] <= date) & (mp_dates["end_date"] >= date)
        return mask.any()

    # iterate through all agreements
    for decision_link in policy.agreement_links.all():
        if not is_valid_date(decision_link.decision.date):
            continue
        if not comparsion_period.is_valid_date(decision_link.decision.date):
            continue
        if decision_link.decision.chamber != chamber:
            continue
        if decision_link.alignment == PolicyDirection.NEUTRAL:
            continue
        if decision_link.strength == PolicyStrength.STRONG:
            if decision_link.alignment == PolicyDirection.AGREE:
                member_score.num_strong_agreements_same += 1
            else:
                member_score.num_strong_agreements_different += 1
        else:
            if decision_link.alignment == PolicyDirection.AGREE:
                member_score.num_agreements_same += 1
            else:
                member_score.num_agreements_different += 1

    # iterate through all divisions
    for decision_link in policy.division_links.all():
        # ignore neutral policies
        if decision_link.alignment == PolicyDirection.NEUTRAL:
            debug_print(f"policy neutral {decision_link.decision.id} - discarded")
            continue
        if decision_link.decision.chamber != chamber:
            debug_print("policy out of chamber - discarded")
            continue

        if not comparsion_period.is_valid_date(decision_link.decision.date):
            debug_print("policy not in comparison period - discarded")
            debug_print(f"date is {decision_link.decision.date}")
            debug_print(
                f"period is {comparsion_period.start_date} - {comparsion_period.end_date}"
            )
            continue

        if not is_valid_date(decision_link.decision.date):
            debug_print("person not a member of this date")
            debug_print(f"date is {decision_link.decision.date}")
            # this person was not a member on this date
            continue

        # get associated votes for this division
        votes = list(decision_link.decision.votes.all())
        if votes[0].division_id != decision_link.decision.id:
            raise ValueError("votes and division_id do not match")
        vote_lookup = {v.person.id: v for v in votes}
        date = decision_link.decision.date

        # get all possible members on this date
        party_mask = (party_members["start_date"] <= date) & (
            party_members["end_date"] >= date
        )
        is_strong = decision_link.strength == PolicyStrength.STRONG
        rel_party_members = party_members[party_mask]
        other_this_vote_score = Score()

        person_ids = rel_party_members["person_id"].astype(int).tolist()

        debug_print(is_strong, decision_link.strength, decision_link.alignment)

        # iterate through members in votes
        vote_assigned = True
        for _, member_series in rel_party_members.iterrows():
            loop_person_id = int(member_series["person_id"])
            is_target = person_id == loop_person_id
            vote = vote_lookup.get(loop_person_id, None)

            if is_target:
                debug_print("this member is the target")
                debug_print(vote)
            if vote is None:
                raise ValueError("Vote not found")

            else:
                if vote_assigned is False:
                    raise ValueError("Previous vote not assigned value")
                vote_assigned = False
                # this member did vote
                # alignment tests if the vote is in the same direction as the policy
                aligned = (
                    vote.vote in [VotePosition.AYE, VotePosition.TELLAYE]
                    and decision_link.alignment == PolicyDirection.AGREE
                ) or (
                    vote.vote in [VotePosition.NO, VotePosition.TELLNO]
                    and decision_link.alignment == PolicyDirection.AGAINST
                )
                is_abstention = vote.vote == VotePosition.ABSTAIN
                is_absent = vote.vote == VotePosition.ABSENT
                if is_target:
                    if is_strong:
                        if aligned:
                            member_score.num_strong_votes_same += 1
                            vote_assigned = True
                        else:
                            if is_abstention:
                                member_score.num_strong_votes_abstain += 1
                                vote_assigned = True
                            else:
                                if is_absent:
                                    member_score.num_strong_votes_absent += 1
                                    vote_assigned = True
                                else:
                                    member_score.num_strong_votes_different += 1
                                    vote_assigned = True
                    else:
                        if aligned:
                            member_score.num_votes_same += 1
                            vote_assigned = True
                        else:
                            if is_abstention:
                                member_score.num_votes_abstain += 1
                                vote_assigned = True
                            else:
                                if is_absent:
                                    member_score.num_votes_absent += 1
                                    vote_assigned = True
                                else:
                                    member_score.num_votes_different += 1
                                    vote_assigned = True
                else:
                    if is_strong:
                        if aligned:
                            other_this_vote_score.num_strong_votes_same += 1
                            vote_assigned = True
                        else:
                            if is_abstention:
                                other_this_vote_score.num_strong_votes_abstain += 1
                                vote_assigned = True
                            else:
                                if is_absent:
                                    other_this_vote_score.num_strong_votes_absent += 1
                                    vote_assigned = True
                                else:
                                    other_this_vote_score.num_strong_votes_different += 1
                                    vote_assigned = True
                    else:
                        if aligned:
                            other_this_vote_score.num_votes_same += 1
                            vote_assigned = True
                        else:
                            if is_abstention:
                                other_this_vote_score.num_votes_abstain += 1
                                vote_assigned = True
                            else:
                                if is_absent:
                                    other_this_vote_score.num_votes_absent += 1
                                    vote_assigned = True
                                else:
                                    other_this_vote_score.num_votes_different += 1
                                    vote_assigned = True

        # for this vote, reduce the score to a fraction - so 'all other mps' cast '1' vote in total.
        if other_this_vote_score.total_votes > 0:
            other_score += other_this_vote_score.reduce()
        debug_print("Appending vote score")
        debug_print(len(other_score.num_comparators))
        other_score.num_comparators.append(len(person_ids) - 1)
        member_score.num_comparators.append(1)
        other_score.num_comparators.sort()
        member_score.num_comparators.sort()

        if other_score.total_votes == 0:
            # assume this is a rare/absent party comparison
            other_score = member_score

    return PolicyComparison(
        target_distribution=member_score, other_distribution=other_score
    )


class ValidationResult(BaseModel):
    slow: PolicyComparison
    fast: PolicyComparison
    results_match: bool


def validate_approach(
    person_id: int,
    policy_id: int,
    party_id: int,
    chamber_id: int,
    period_id: int,
    debug: bool = False,
) -> ValidationResult:
    """
    This function validates that the fast SQL approach reaches the same conclusions as the easier to follow
    Python function.
    """

    duck = get_connected_duck()

    # get fast approach
    df = (
        PolicyPivotTable(
            person_id=person_id,
            party_id=party_id,
            chamber_id=chamber_id,
        )
        .compile(duck)
        .df()
        .fillna(0)
    )

    # filter to the policy and period_id

    mask = (df["policy_id"] == policy_id) & (df["period_id"] == period_id)
    df = df[mask]

    di = df.set_index("is_target").to_dict("index")

    fast_approach = PolicyComparison(
        target_distribution=(td := Score.model_validate(di[1]) if 1 in di else Score()),
        other_distribution=Score.model_validate(di.get(0, td)),
    )

    # get slow approach
    slow_approach = get_scores_slow(
        person_id=person_id,
        policy_id=policy_id,
        party_id=party_id,
        chamber_id=chamber_id,
        period_id=period_id,
        debug=debug,
    )

    # validate if they're reaching the same conclusion
    result = slow_approach == fast_approach

    return ValidationResult(
        slow=slow_approach, fast=fast_approach, results_match=result
    )


def test_policy_sample(sample: int = 50, policy_id: int | None = None) -> bool:
    """
    Pick a random sample of policies and people and validate that the fast and slow approaches
    reach the same conclusion.
    """

    path = Path("data", "compiled", "relevant_person_policy_period.parquet")

    df = pd.read_parquet(path)

    if policy_id:
        df = df[df["policy_id"] == policy_id]

    df = df.sample(sample).fillna(0)

    has_errors = False

    for _, row in tqdm(df.iterrows(), total=len(df)):
        policy_id = int(row["policy_id"])
        person_id = int(row["person_id"])
        party_id = int(row["party_id"])
        chamber_id = int(row["chamber_id"])
        period_id = int(row["period_id"])

        result = validate_approach(
            person_id=person_id,
            policy_id=policy_id,
            party_id=party_id,
            chamber_id=chamber_id,
            period_id=period_id,
        )

        summary = {
            "policy_id": policy_id,
            "person_id": person_id,
            "party_id": party_id,
            "chamber_id": chamber_id,
            "period_id": period_id,
            "result": result.results_match,
        }

        if not result.results_match:
            rich.print(summary)
            has_errors = True

    if not has_errors:
        rich.print("[green]No errors found[/green]")
    return has_errors


class Command(BaseCommand):
    help = "Slow validate policy generation"
    message = ""

    def add_arguments(self, parser):
        parser.add_argument(
            "-q", "--quiet", action="store_true", help="Silence progress bars."
        )

        # I need three options here
        # an --model level an --group level and an --all level

        # I need to be able to run a single model, a group of models or all models

        parser.add_argument(
            "--sample",
            type=int,
            help="Test a sample of policies fast and slow",
            nargs="?",
            default=50,
        )

        parser.add_argument(
            "--policy_id",
            type=int,
            help="Test a single policy",
            nargs="?",
            default=None,
        )

    def handle(
        self,
        *args,
        sample: int = 50,
        policy_id: int | None = None,
        quiet: bool = False,
        **options,
    ):
        if not quiet:
            rich.print("[bold]Validating policy generation[/bold]")

        has_errors = test_policy_sample(sample=sample, policy_id=policy_id)

        if has_errors:
            raise ValueError("Errors found in policy generation")
