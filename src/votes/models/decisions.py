from __future__ import annotations

import datetime
from typing import Optional

from django.db import models

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


class Chamber(DjangoVoteModel):
    slug: ChamberSlug
    member_plural: str
    name: str
    comparison_periods: DummyOneToMany[PolicyComparisonPeriod] = related_name("chamber")

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
    voting_cluster: str = ""
    total_possible_members: int
    votes: DummyOneToMany[Vote] = related_name("division")
    overall_breakdown: DummyOneToMany[DivisionBreakdown] = related_name("division")
    party_breakdowns: DummyOneToMany[DivisionPartyBreakdown] = related_name("division")
    is_gov_breakdowns: DummyOneToMany[DivisionsIsGovBreakdown] = related_name(
        "division"
    )


class DivisionTag(DjangoVoteModel):
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("analyses")
    tag_type: TagType
    analysis_data: str


class DivisionBreakdown(DjangoVoteModel):
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("breakdowns")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # not sure why this is needed, but coming back as strin
        self.vote = VotePosition(int(self.vote))
        self.effective_vote = VotePosition(int(self.effective_vote))


class Agreement(DjangoVoteModel):
    key: str
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Chamber] = related_name("agreements")
    date: datetime.date
    decision_ref: str
    decision_name: str
    voting_cluster: str = "Agreement"


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
