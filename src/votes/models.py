from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol, Type, TypeVar

from django.db import models
from django.urls import reverse

import markdown
import numpy as np
import pandas as pd
from numpy import nan

from twfy_votes.helpers.base_model import DjangoVoteModel
from twfy_votes.helpers.typed_django.models import (
    DoNothingForeignKey,
    Dummy,
    DummyManyToMany,
    DummyOneToMany,
    ManyToMany,
    PrimaryKey,
    TextField,
    field,
    related_name,
)

from .consts import (
    ChamberSlug,
    MotionType,
    OrganisationType,
    PolicyDirection,
    PolicyGroupSlug,
    PolicyStatus,
    PolicyStrength,
    PowersAnalysis,
    RebellionPeriodType,
    StrengthMeaning,
    TagType,
    VotePosition,
)
from .policy_generation.scoring import (
    ScoringFuncProtocol,
    SimplifiedScore,
)

if TYPE_CHECKING:
    from .models import (
        Chamber,
        PolicyComparisonPeriod,
        RebellionRate,
        Vote,
        VoteDistribution,
    )


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

    @property
    def decision_type(self) -> str: ...

    @property
    def motion_uses_powers(self) -> PowersAnalysis: ...

    @property
    def motion(self) -> Motion | None: ...

    def safe_decision_name(self) -> str: ...

    def url(self) -> str: ...

    def twfy_link(self) -> str: ...

    def motion_speech_url(self) -> str: ...


DecisionProtocolType = TypeVar("DecisionProtocolType", bound=DecisionProtocol)


def is_valid_decision_model(
    klass: Type[DecisionProtocolType],
) -> Type[DecisionProtocolType]:
    return klass


@dataclass
class DistributionGroup:
    party: Organization
    chamber: Chamber
    period: PolicyComparisonPeriod

    def key(self):
        return f"{self.party.id}-{self.chamber.id}-{self.period.id}"


class Person(DjangoVoteModel):
    id: PrimaryKey = None
    name: str
    memberships: DummyOneToMany["Membership"] = related_name("person")
    votes: DummyOneToMany[Vote] = related_name("person")
    vote_distributions: DummyOneToMany[VoteDistribution] = related_name("person")
    rebellion_rates: DummyOneToMany[RebellionRate] = related_name("person")

    def str_id(self):
        return f"uk.org.publicwhip/person/{self.id}"

    def votes_url(self, year: str = "all"):
        return reverse("person_votes", kwargs={"person_id": self.id, "year": year})

    def rebellion_rate_df(self):
        items = self.rebellion_rates.filter(
            period_type=RebellionPeriodType.YEAR
        ).order_by("-period_number")
        df = pd.DataFrame(
            [
                {
                    "Year": UrlColumn(
                        reverse("person_votes", args=[self.id, r.period_number]),
                        str(r.period_number),
                    ),
                    "Party alignment": 1 - r.value,
                    "Total votes": r.total_votes,
                }
                for r in items
            ]
        )

        return df

    def policy_distribution_groups(self):
        groups: list[DistributionGroup] = []
        distributions = self.vote_distributions.all().prefetch_related(
            "period", "chamber", "party"
        )
        # iterate through this and create unique groups

        existing_keys = []

        for distribution in distributions:
            group = DistributionGroup(
                party=distribution.party,
                chamber=distribution.chamber,
                period=distribution.period,
            )
            if group.key() not in existing_keys:
                groups.append(group)
                existing_keys.append(group.key())

        return groups

    @classmethod
    def current(cls):
        """
        Those with a membership that is current.
        """
        return cls.objects.filter(memberships__end_date__gte=datetime.date.today())

    def membership_in_chamber_on_date(
        self, chamber_slug: ChamberSlug, date: datetime.date
    ) -> Membership:
        membership = self.memberships.filter(
            chamber_slug=chamber_slug, start_date__lte=date, end_date__gte=date
        ).first()
        if membership:
            return membership
        else:
            raise ValueError(
                f"{self.name} was not a member of {chamber_slug} on {date}"
            )

    def votes_df(self, year: int | None = None) -> pd.DataFrame:
        if year:
            votes_query = self.votes.filter(division__date__year=year)
        else:
            votes_query = self.votes.all()

        data = [
            {
                "Date": v.division.date,
                "Division": UrlColumn(
                    url=v.division.url(), text=v.division.division_name
                ),
                "Vote": v.vote_desc(),
                "Party alignment": (
                    1
                    - (
                        v.diff_from_party_average
                        if v.diff_from_party_average is not None
                        else np.nan
                    )
                ),
            }
            for v in votes_query
            if v.division is not None
        ]

        # sort by data decending
        data = sorted(data, key=lambda x: x["Date"], reverse=True)

        return pd.DataFrame(data=data)


class Organization(DjangoVoteModel):
    id: PrimaryKey = None
    slug: str
    name: str
    classification: OrganisationType = OrganisationType.UNKNOWN
    org_memberships: DummyOneToMany["Membership"] = related_name("organization")
    party_memberships: DummyOneToMany["Membership"] = related_name("on_behalf_of")


class OrgMembershipCount(DjangoVoteModel):
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int] = 0
    chamber: DoNothingForeignKey[Organization] = related_name("org_membership_counts")
    start_date: datetime.date
    end_date: datetime.date
    count: int


class Membership(DjangoVoteModel):
    """
    A timed connection between a person and a post.
    """

    id: PrimaryKey = None
    person_id: Dummy[int] = 0
    person: DoNothingForeignKey[Person] = related_name("memberships")
    start_date: datetime.date
    end_date: datetime.date
    party_slug: str
    effective_party_slug: str
    party_id: Dummy[Optional[int]] = None
    party: DoNothingForeignKey[Organization] = field(
        default=None, null=True, related_name="party_memberships"
    )
    effective_party_id: Dummy[Optional[int]] = None
    effective_party: DoNothingForeignKey[Organization] = field(
        default=None, null=True, related_name="effective_party_memberships"
    )
    chamber_id: Dummy[Optional[int]] = None
    chamber: DoNothingForeignKey[Chamber] = field(
        default=None, null=True, related_name="org_memberships"
    )
    chamber_slug: str
    post_label: str
    area_name: str


class Chamber(DjangoVoteModel):
    slug: ChamberSlug
    member_plural: str
    name: str
    comparison_periods: DummyOneToMany[PolicyComparisonPeriod] = related_name("chamber")

    def last_decision_date(self) -> Optional[datetime.date]:
        last_division = Division.objects.filter(chamber=self).order_by("-date").first()
        last_agreement = (
            Agreement.objects.filter(chamber=self).order_by("-date").first()
        )

        match (last_division, last_agreement):
            case (None, None):
                return None
            case (None, last_agreement):
                return last_agreement.date  # type: ignore
            case (last_division, None):
                return last_division.date
            case (last_division, last_agreement):
                return max(last_division.date, last_agreement.date)

    @classmethod
    def with_votes(cls):
        return cls.objects.all().exclude(slug=ChamberSlug.NI)

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


class Motion(DjangoVoteModel):
    gid: str
    speech_id: str
    date: datetime.date
    title: str
    text: TextField
    motion_type: MotionType

    def is_nonaction_vote(self, quiet: bool = True) -> bool:
        """
        Analyse the text of a motion to determine if it is a non-action motion
        """
        non_action_phrases = [
            "believes",
            "regrets",
            "notes with approval",
            "expressed approval",
            "welcomes",
            "is concerned",
            "calls on the",
            "recognises",
            "takes note",
            "agrees with the goverment's decision",
            "regret that the gracious speech",
            "do now adjourn",
            "has considered",
        ]
        action_phrases = [
            "orders that",
            "requires the goverment",
            "censures",
            "declines to give a second reading",
        ]

        reduced_text = self.text.lower()

        score = 0
        for phrase in non_action_phrases:
            if phrase in reduced_text:
                if not quiet:
                    print(f"matched {phrase}")
                score += 1

        for phrase in action_phrases:
            if phrase in reduced_text:
                if not quiet:
                    print(f"matched {phrase}- is action")
                score = 0

        return score > 0

    def motion_uses_powers(self) -> PowersAnalysis:
        """
        We only need to do vote analysis for votes that aren't inherently using powers based on
        classification further up.
        """

        if self.motion_type in [
            MotionType.ADJOURNMENT,
            MotionType.OTHER,
            MotionType.GOVERNMENT_AGENDA,
        ]:
            if self.is_nonaction_vote():
                return PowersAnalysis.DOES_NOT_USE_POWERS
            else:
                return PowersAnalysis.USES_POWERS
        else:
            return PowersAnalysis.USES_POWERS

    def motion_type_nice(self):
        return str(self.motion_type).replace("_", " ").title()

    def nice_html(self) -> str:
        return markdown.markdown(self.nice_text(), extensions=["tables"])

    def nice_text(self) -> str:
        text = self.text

        lines = text.split("\n")

        # we want to add a full empty line before and after markdown tables
        # we also have a situation when we get lots of tables in a row it's not immediately obv
        # when the next one starts
        # but on the *second* line we get |----
        # so can retrospectively add a line break there

        new_lines = []
        in_table = False
        for i, line in enumerate(lines):
            if line.startswith("|"):
                if not in_table:
                    new_lines.append("")
                    in_table = True
                new_lines.append(line)
                if line.startswith("|----"):
                    # insert a line break two rows up
                    new_lines.insert(-2, "")
            else:
                if in_table:
                    in_table = False
                    new_lines.append(line)
                    new_lines.append("")
                    new_lines.append("")
                else:
                    new_lines.append(line)

        text = "\n".join(new_lines)

        # add newline after each semi colon or full stop.
        text = text.replace(";", ";\n\n")
        text = text.replace("“SCHEDULE", "\n\n“SCHEDULE")

        return text


@is_valid_decision_model
class Division(DjangoVoteModel):
    key: str
    chamber_slug: ChamberSlug
    chamber_id: Dummy[int]
    chamber: DoNothingForeignKey[Chamber] = related_name("divisions")
    division_info_source: str = ""
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
    motion_id: Dummy[Optional[int]] = None
    motion: Optional[Motion] = field(
        models.ForeignKey,
        to=Motion,
        on_delete=models.DO_NOTHING,
        null=True,
        default=None,
        related_name="divisions",
    )

    def motion_type(self) -> MotionType:
        if self.motion:
            return self.motion.motion_type
        return MotionType.UNKNOWN

    def motion_speech_url(self) -> str:
        if self.motion:
            gid = self.motion.speech_id.split("/")[-1]
            return self.chamber.twfy_debate_link(gid)
        return ""

    def single_breakdown(self):
        ob = self.overall_breakdowns.first()
        if ob:
            return ob
        raise ValueError("No overall breakdown found")

    def voting_cluster(self) -> dict[str, str]:
        lookup = {
            "opp_strong_aye_gov_strong_no": "Strong conflict: Opposition proposes",
            "gov_aye_opp_lean_no": "Divided opposition: Government Aye, Opposition divided",
            "opp_aye_weak_gov_no": "Medium conflict: Opposition Aye, Government No",
            "gov_aye_opp_weak_no": "Nominal opposition: Government Aye Opposition Weak No",
            "gov_no_opp_lean_no": "Multi-party against: Government No, Opposition divided",
            "low_participation": "Low participation vote",
            "gov_strong_aye_opp_strong_no": "Strong conflict: Gov proposes",
            "cross_party_aye": "Cross party aye",
        }

        tag = self.tags.filter(tag_type=TagType.GOV_CLUSTERS).first()
        data = tag.analysis_data if tag else "Unknown"
        desc = lookup.get(data, "Unknown")

        return {"tag": data, "desc": desc}

    def twfy_link(self) -> str:
        gid = self.source_gid.split("/")[-1]

        return self.chamber.twfy_debate_link(gid)

    @property
    def decision_type(self) -> str:
        return "Division"

    @property
    def motion_uses_powers(self) -> PowersAnalysis:
        if self.motion:
            return self.motion.motion_uses_powers()
        else:
            return PowersAnalysis.INSUFFICENT_INFO

    def url(self) -> str:
        return reverse(
            "division", args=[self.chamber_slug, self.date, self.division_number]
        )

    def safe_decision_name(self) -> str:
        if self.motion:
            return self.motion.title
        return self.division_name

    def party_breakdown_df(self) -> pd.DataFrame:
        data = [
            {
                "Grouping": x.party.name,
                f"{self.chamber.member_plural} on date": x.vote_participant_count,
                "Vote participant count": x.signed_votes,
                "For motion": x.for_motion,
                "Against motion": x.against_motion,
                "Neutral motion": x.neutral_motion,
                "Absent motion": x.absent_motion,
                "Party turnout": x.signed_votes / x.vote_participant_count,
                "For motion percentage": x.for_motion_percentage
                if not pd.isna(x.for_motion_percentage)
                else "-",
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
            "Vote participant count": overall_breakdown.signed_votes,
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
                "Vote participant count": x.signed_votes,
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

        for d in data:
            if pd.isna(d["Party alignment"]):
                d["Party alignment"] = "-"

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
    motion_id: Dummy[Optional[int]] = None
    motion: Optional[Motion] = field(
        models.ForeignKey,
        to=Motion,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="agreements",
        default=None,
    )

    def motion_type(self) -> MotionType:
        if self.motion:
            return self.motion.motion_type
        return MotionType.UNKNOWN

    def motion_speech_url(self) -> str:
        if self.motion:
            gid = self.motion.speech_id.split("/")[-1]
            return self.chamber.twfy_debate_link(gid)
        return ""

    def voting_cluster(self) -> dict[str, str]:
        return {"tag": "Agreement", "desc": "Agreement"}

    def safe_decision_name(self) -> str:
        return self.decision_name or "[missing title]"

    def twfy_link(self) -> str:
        gid = self.decision_ref.split("/")[-1]
        # remove the final .number
        gid = f"{self.date.isoformat()}.".join(gid.split(".")[:-1])
        return self.chamber.twfy_debate_link(gid)

    def votes_df(self) -> pd.DataFrame:
        relevant_memberships = Membership.objects.filter(
            chamber=self.chamber, start_date__lte=self.date, end_date__gte=self.date
        )
        data = [
            {
                "Person": UrlColumn(url=m.person.votes_url(), text=m.person.name),
                "Party": m.party.name,
                "Vote": "Collective",
            }
            for m in relevant_memberships
        ]

        return pd.DataFrame(data=data)

    @property
    def decision_type(self) -> str:
        return "Agreement"

    @property
    def motion_uses_powers(self) -> PowersAnalysis:
        if self.motion:
            return self.motion.motion_uses_powers()
        else:
            return PowersAnalysis.INSUFFICENT_INFO

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
    vote_distributions: DummyOneToMany[VoteDistribution] = related_name("policy")
    policy_hash: str

    def url(self) -> str:
        return reverse("policy", args=[self.id])

    def decision_df(self) -> pd.DataFrame:
        """ """
        division_data = [
            {
                "month": x.decision.date.strftime("%Y-%m"),
                "decision": UrlColumn(
                    url=x.decision.url(), text=x.decision.safe_decision_name()
                ),
                "alignment": x.alignment,
                "strength": x.strength,
                "decision type": "Division",
                "uses powers": x.decision.motion_uses_powers,
                "voting cluster": x.decision.voting_cluster()["desc"],
                "participant count": x.decision.single_breakdown().signed_votes,
            }
            for x in self.division_links.all()
        ]

        agreement_data = [
            {
                "month": x.decision.date.strftime("%Y-%m"),
                "decision": UrlColumn(
                    url=x.decision.url(), text=x.decision.safe_decision_name()
                ),
                "alignment": x.alignment,
                "strength": x.strength,
                "decision type": "Agreement",
                "uses powers": x.decision.motion_uses_powers,
                "voting cluster": x.decision.voting_cluster()["desc"],
                "participant count": 0,
            }
            for x in self.agreement_links.all()
        ]

        df = pd.DataFrame(data=division_data + agreement_data)
        # sort by month
        df = df.sort_values(by="month")
        return df

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

    @property
    def total_votes(self) -> float:
        return (
            self.num_votes_same
            + self.num_strong_votes_same
            + self.num_votes_different
            + self.num_strong_votes_different
            + self.num_votes_absent
            + self.num_strong_votes_absent
            + self.num_votes_abstain
            + self.num_strong_votes_abstain
        )

    @property
    def verbose_score(self) -> str:
        match self.distance_score:
            case s if 0 <= s <= 0.05:
                return "Consistently voted for"
            case s if 0.05 < s <= 0.15:
                return "Almost always voted for"
            case s if 0.15 < s <= 0.4:
                return "Generally voted for"
            case s if 0.4 < s <= 0.6:
                return "Voted a mixture of for and against"
            case s if 0.6 < s <= 0.85:
                return "Generally voted against"
            case s if 0.85 < s <= 0.95:
                return "Almost always voted against"
            case s if 0.95 < s <= 1:
                return "Consistently voted against"
            case s if s == -1:
                return "No data available"
            case _:
                raise ValueError("Score must be between 0 and 1")


class RebellionRate(DjangoVoteModel):
    person_id: Dummy[int] = 0
    person: DoNothingForeignKey[Person] = related_name("rebellion_rates")
    period_type: RebellionPeriodType
    period_number: int
    value: float
    total_votes: int

    def composite_key(self) -> str:
        return f"{self.person_id}-{self.period_type}-{self.period_number}"
