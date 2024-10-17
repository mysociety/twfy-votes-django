from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional, Protocol, Type, TypeVar

from django.db import models
from django.urls import reverse

import pandas as pd
from numpy import nan

from twfy_votes.helpers.typed_django.models import (
    DoNothingForeignKey,
    Dummy,
    DummyManyToMany,
    DummyOneToMany,
    ManyToMany,
    TextField,
    field,
    related_name,
)

from ..consts import (
    ChamberSlug,
    PolicyDirection,
    PolicyGroupSlug,
    PolicyStatus,
    PolicyStrength,
    StrengthMeaning,
    TagType,
    VotePosition,
)
from ..policy_generation.scoring import (
    ScoringFuncProtocol,
    SimplifiedScore,
)
from .base_model import DjangoVoteModel
from .people import Membership, Organization, Person


@dataclass
class UrlColumn:
    url: str
    text: str

    def __str__(self) -> str:
        return f'<a href="{self.url}">{self.text}</a>'


class DecisionProtocol(Protocol):
    """
    Use this to define types that all decisiosn types should impliemnt
    """

    def vote_type(self) -> str: ...

    def motion_uses_powers(self) -> str: ...

    def url(self) -> str: ...

    def twfy_link(self) -> str: ...


DecisionProtocolType = TypeVar("DecisionProtocolType", bound=DecisionProtocol)


def is_valid_decision_model(
    klass: Type[DecisionProtocolType],
) -> Type[DecisionProtocolType]:
    return klass


class Chamber(DjangoVoteModel):
    slug: ChamberSlug
    member_plural: str
    name: str
    comparison_periods: DummyOneToMany[PolicyComparisonPeriod] = related_name("chamber")

    def year_range(self) -> list[int]:
        """
        Return a list of all years there is a division or agreement for this chamber.
        """
        rel_divisions = [x.date.year for x in Division.objects.filter(chamber=self)]
        rel_agreements = [x.date.year for x in Agreement.objects.filter(chamber=self)]

        years = rel_divisions + rel_agreements
        return sorted(list(set(years)), reverse=True)

    @property
    def pw_alias(self):
        # Alias for internal debate storage
        match self.slug:
            case ChamberSlug.COMMONS:
                return "debate"
            case _:
                return self.twfy_alias

    @property
    def twfy_alias(self):
        # Alias for internal debate storage
        match self.slug:
            case ChamberSlug.COMMONS:
                return "debates"
            case ChamberSlug.LORDS:
                return "lords"
            case ChamberSlug.SCOTLAND:
                return "sp"
            case ChamberSlug.WALES:
                return "senedd"
            case ChamberSlug.NI:
                return "ni"
            case _:
                raise ValueError(f"Invalid house slug {self.slug}")

    def twfy_debate_link(self, gid: str) -> str:
        return f"https://www.theyworkforyou.com/{self.twfy_alias}/?id={gid}"


class GovernmentParty(DjangoVoteModel):
    label: str
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Chamber] = related_name("government_parties")
    party: str
    start_date: datetime.date
    end_date: datetime.date


class PolicyComparisonPeriod(DjangoVoteModel):
    slug: str
    description: str
    start_date: datetime.date
    end_date: datetime.date
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Chamber] = related_name("comparison_periods")

    def is_valid_date(self, date: datetime.date) -> bool:
        return self.start_date <= date <= self.end_date


@is_valid_decision_model
class Division(DjangoVoteModel):
    key: str
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int]
    chamber: DoNothingForeignKey[Chamber] = related_name("divisions")
    date: datetime.date
    division_number: int
    division_name: str
    source_gid: str
    debate_gid: str
    total_possible_members: int
    votes: DummyOneToMany[Vote] = related_name("division")
    overall_breakdowns: DummyOneToMany[DivisionBreakdown] = related_name("division")
    party_breakdowns: DummyOneToMany[DivisionPartyBreakdown] = related_name("division")
    is_gov_breakdowns: DummyOneToMany[DivisionsIsGovBreakdown] = related_name(
        "division"
    )
    tags: DummyManyToMany[DivisionTag] = related_name("division")

    def voting_cluster(self) -> dict[str, str]:
        lookup = {
            "opp_strong_aye_gov_strong_no": "Strong conflict: Opposition proposes",
            "gov_aye_opp_lean_no": "Divided ppposition: Government Aye, Opposition lean No",
            "opp_aye_weak_gov_no": "Low stakes: Opposition Aye, Weak Government No",
            "gov_aye_opp_weak_no": "Nominal opposition: Government Aye Opposition Weak No",
            "gov_no_opp_lean_no": "Shut it down: Rough consensus against",
            "low_participation": "Low Participation vote",
            "gov_strong_aye_opp_strong_no": "Strong Conflict: Gov proposes",
            "cross_party_aye": "Cross Party Aye",
        }

        tag = self.tags.filter(tag_type=TagType.GOV_CLUSTERS).first()
        data = tag.analysis_data if tag else "Unknown"
        desc = lookup.get(data, "Unknown")

        return {"tag": data, "desc": desc}

    def twfy_link(self) -> str:
        gid = self.source_gid.split("/")[-1]

        return self.chamber.twfy_debate_link(gid)

    def vote_type(self) -> str:
        return "Division"

    def motion_uses_powers(self) -> str:
        return "Unknown"

    def url(self) -> str:
        return reverse(
            "division", args=[self.chamber_slug, self.date, self.division_number]
        )

    def safe_decision_name(self) -> str:
        return self.key

    def party_breakdown_df(self) -> pd.DataFrame:
        data = [
            {
                "Grouping": x.party.name,
                f"{self.chamber.member_plural} on date": x.vote_participant_count,
                "For motion": x.for_motion,
                "Against motion": x.against_motion,
                "Neutral motion": x.neutral_motion,
                "Absent motion": x.absent_motion,
                "Party turnout": x.signed_votes / x.vote_participant_count,
                "For motion percentage": x.for_motion_percentage,
            }
            for x in self.party_breakdowns.all()
        ]

        return pd.DataFrame(data=data)

    def gov_breakdown_df(self) -> pd.DataFrame:
        overall_breakdown = self.overall_breakdowns.first()
        if overall_breakdown is None:
            raise ValueError("No overall breakdown found")

        overall_breakdown_dict = {
            "Grouping": f"All {self.chamber.member_plural}",
            f"{self.chamber.member_plural} on date": overall_breakdown.vote_participant_count,
            "For motion": overall_breakdown.for_motion,
            "Against motion": overall_breakdown.against_motion,
            "Neutral motion": overall_breakdown.neutral_motion,
            "Absent motion": overall_breakdown.absent_motion,
            "Turnout": overall_breakdown.signed_votes
            / overall_breakdown.vote_participant_count,
            "For motion percentage": overall_breakdown.for_motion_percentage,
        }

        gov_breakdowns = [
            {
                "Grouping": "Government" if x.is_gov else "Opposition",
                f"{self.chamber.member_plural} on date": x.vote_participant_count,
                "For motion": x.for_motion,
                "Against motion": x.against_motion,
                "Neutral motion": x.neutral_motion,
                "Absent motion": x.absent_motion,
                "Turnout": x.signed_votes / x.vote_participant_count,
                "For motion percentage": x.for_motion_percentage,
            }
            for x in self.is_gov_breakdowns.all()
        ]

        all_breakdowns = [overall_breakdown_dict] + gov_breakdowns

        all_breakdowns = [dict(x) for x in all_breakdowns]
        df = pd.DataFrame(data=all_breakdowns)

        return df

    def votes_df(self) -> pd.DataFrame:
        relevant_memberships = Membership.objects.filter(
            chamber=self.chamber, start_date__lte=self.date, end_date__gte=self.date
        )
        person_to_membership_map = {x.person_id: x for x in relevant_memberships}

        data = [
            {
                "Person": UrlColumn(url=v.person.votes_url(), text=v.person.name),
                "Party": person_to_membership_map[v.person_id].party.name,
                "Vote": v.vote_desc(),
                "Party alignment": 1
                - (
                    v.diff_from_party_average
                    if v.diff_from_party_average is not None
                    else nan
                ),
            }
            for v in self.votes.all()
        ]

        return pd.DataFrame(data=data)


class DivisionTag(DjangoVoteModel):
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("tags")
    tag_type: TagType
    analysis_data: str


class DivisionBreakdown(DjangoVoteModel):
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("overall_breakdowns")
    vote_participant_count: int
    total_possible_members: int
    for_motion: int
    against_motion: int
    neutral_motion: int
    absent_motion: int
    signed_votes: int
    motion_majority: int
    for_motion_percentage: float
    motion_result_int: int

    def motion_result(self) -> str:
        match self.motion_result_int:
            case 1:
                return "Success"
            case 0:
                return "Tie"
            case -1:
                return "Failure"
            case _:
                raise ValueError(f"Invalid motion result {self.motion_result_int}")


class DivisionsIsGovBreakdown(DjangoVoteModel):
    is_gov: bool
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("is_gov_breakdowns")
    vote_participant_count: int
    total_possible_members: int
    for_motion: int
    against_motion: int
    neutral_motion: int
    absent_motion: int
    signed_votes: int
    motion_majority: int
    for_motion_percentage: float
    motion_result_int: int


class DivisionPartyBreakdown(DjangoVoteModel):
    party_id: Dummy[int]
    party: DoNothingForeignKey[Organization] = related_name("party_breakdowns")
    party_slug: str
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("party_breakdowns")
    vote_participant_count: int
    total_possible_members: int
    for_motion: int
    against_motion: int
    neutral_motion: int
    absent_motion: int
    signed_votes: int
    motion_majority: int
    for_motion_percentage: float
    motion_result_int: int


class Vote(DjangoVoteModel):
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("votes")
    vote: VotePosition
    effective_vote: VotePosition
    membership_id: Dummy[int]
    membership: DoNothingForeignKey[Membership] = related_name("votes")
    person_id: Dummy[int]
    person: DoNothingForeignKey[Person] = related_name("votes")
    is_gov: bool
    effective_vote_float: Optional[float] = field(models.FloatField, null=True)
    diff_from_party_average: Optional[float] = field(models.FloatField, null=True)

    def vote_desc(self) -> str:
        return self.vote.name.title()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # not sure why this is needed, but coming back as strin
        self.vote = VotePosition(int(self.vote))
        self.effective_vote = VotePosition(int(self.effective_vote))


@is_valid_decision_model
class Agreement(DjangoVoteModel):
    key: str
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Chamber] = related_name("agreements")
    date: datetime.date
    decision_ref: str
    decision_name: str

    def voting_cluster(self) -> dict[str, str]:
        return {"tag": "Unknown", "desc": "Unknown"}

    def safe_decision_name(self) -> str:
        return self.key

    def twfy_link(self) -> str:
        gid = self.decision_ref.split("/")[-1]
        return self.chamber.twfy_debate_link(gid)

    def vote_type(self) -> str:
        return "Agreement"

    def motion_uses_powers(self) -> str:
        return "Unknown"

    def url(self) -> str:
        return reverse(
            "agreement", args=[self.chamber_slug, self.date, self.decision_ref]
        )


class PolicyGroup(DjangoVoteModel):
    slug: PolicyGroupSlug
    description: str
    policies: DummyManyToMany[Policy] = related_name("groups")


class Policy(DjangoVoteModel):
    """
    Version of policy object for reading and writing from basic storage.
    Doesn't store full details of related decisions etc.
    """

    name: str
    context_description: TextField
    policy_description: TextField
    notes: TextField = ""
    status: PolicyStatus
    strength_meaning: StrengthMeaning = StrengthMeaning.SIMPLIFIED
    highlightable: bool = False
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Chamber] = related_name("policies")
    groups: ManyToMany[PolicyGroup] = related_name("policies")
    division_links: DummyOneToMany[PolicyDivisionLink] = related_name("policy")
    agreement_links: DummyOneToMany[PolicyAgreementLink] = related_name("policy")
    policy_hash: str

    def get_scoring_function(self) -> ScoringFuncProtocol:
        match self.strength_meaning:
            case StrengthMeaning.SIMPLIFIED:
                return SimplifiedScore
            case _:
                raise ValueError(f"Invalid strength meaning {self.strength_meaning}")


class BasePolicyDecisionLink(DjangoVoteModel, abstract=True):
    alignment: PolicyDirection
    strength: PolicyStrength = PolicyStrength.WEAK
    notes: str = ""


class PolicyDivisionLink(BasePolicyDecisionLink):
    policy_id: Dummy[int] = 0
    policy: DoNothingForeignKey[Policy] = related_name("division_links")
    decision_id: Dummy[int] = 0
    decision: DoNothingForeignKey[Division] = related_name("division_links")


class PolicyAgreementLink(BasePolicyDecisionLink):
    policy_id: Dummy[int] = 0
    policy: DoNothingForeignKey[Policy] = related_name("agreement_links")
    decision_id: Dummy[int] = 0
    decision: DoNothingForeignKey[Agreement] = related_name("agreement_links")


class VoteDistribution(DjangoVoteModel):
    """
    Store the breakdown of votes associated with a policy
    and either a person or a comparison.
    """

    policy_id: Dummy[int] = 0
    policy: DoNothingForeignKey[Policy] = related_name("vote_distributions")
    person_id: Dummy[int] = 0
    person: DoNothingForeignKey[Person] = related_name("vote_distributions")
    period_id: Dummy[int] = 0
    period: DoNothingForeignKey[PolicyComparisonPeriod] = related_name(
        "vote_distributions"
    )
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Chamber] = related_name("vote_distributions")
    party_id: Dummy[int | None] = None
    party: DoNothingForeignKey[Organization] = field(
        default=None, null=True, related_name="vote_distributions"
    )
    is_target: int
    num_votes_same: float
    num_strong_votes_same: float
    num_votes_different: float
    num_strong_votes_different: float
    num_votes_absent: float
    num_strong_votes_absent: float
    num_votes_abstain: float
    num_strong_votes_abstain: float
    num_agreements_same: float
    num_strong_agreements_same: float
    num_agreements_different: float
    num_strong_agreements_different: float
    start_year: int
    end_year: int
    distance_score: float
