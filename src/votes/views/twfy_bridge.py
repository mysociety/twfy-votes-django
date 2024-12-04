"""
This is a bridge between the modern data model and the old public whip data model.
Which is the current import into theyworkforyou
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from ..consts import ChamberSlug, PolicyDirection, PolicyStrength, VotePosition
from ..models import (
    Chamber,
    Division,
    DivisionBreakdown,
    Policy,
    Vote,
    VoteDistribution,
)
from .helper_models import PairedPersonDistributions


class ReducedPersonPolicyLink(BaseModel):
    person_id: str
    policy_id: int
    comparison_period: str
    comparison_party: str
    chamber: ChamberSlug
    person_distance_from_policy: float
    comparison_distance_from_policy: float
    comparison_score_diff: float
    count_present: int
    count_absent: int
    start_year: int
    end_year: int
    no_party_comparison: bool


class ValidOrganizationType(StrEnum):
    COMMONS = "uk.parliament.commons"
    LORDS = "uk.parliament.lords"
    SCOTTISH_PARLIAMENT = "scottish.parliament"


class PopoloVoteOption(StrEnum):
    AYE = "aye"
    TELLNO = "tellno"
    TELLAYE = "tellaye"
    NO = "no"
    BOTH = "both"
    ABSENT = "absent"


class PopoloVoteType(StrEnum):
    AYE = "aye"
    NO = "no"
    BOTH = "both"
    AYE3 = "aye3"
    NO3 = "no3"
    BOTH3 = "both3"

    @classmethod
    def from_modern(cls, direction: PolicyDirection, strength: PolicyStrength):
        if direction == PolicyDirection.AGREE:
            if strength == PolicyStrength.STRONG:
                return cls.AYE3
            elif strength == PolicyStrength.WEAK:
                return cls.AYE
        elif direction == PolicyDirection.AGAINST:
            if strength == PolicyStrength.STRONG:
                return cls.NO3
            elif strength == PolicyStrength.WEAK:
                return cls.NO
        elif direction == PolicyDirection.NEUTRAL:
            return cls.BOTH


class PopoloDirection(StrEnum):
    MAJORITY_STRONG = "Majority (strong)"
    MAJORITY_WEAK = "Majority"
    MINORITY_STRONG = "minority (strong)"
    MINORITY_WEAK = "minority"
    ABSTAIN = "abstention"


class PopoloVoteCount(BaseModel):
    option: PopoloVoteOption
    value: int


class PopoloVote(BaseModel):
    id: str
    option: PopoloVoteOption

    @classmethod
    def from_vote_unvalidated(cls, vote: Vote):
        match vote.vote:
            case VotePosition.AYE:
                option = PopoloVoteOption.AYE
            case VotePosition.NO:
                option = PopoloVoteOption.NO
            case VotePosition.ABSTAIN:
                option = PopoloVoteOption.BOTH
            case VotePosition.ABSENT:
                option = PopoloVoteOption.ABSENT
            case VotePosition.TELLNO:
                option = PopoloVoteOption.TELLNO
            case VotePosition.TELLAYE:
                option = PopoloVoteOption.TELLAYE
            case _:
                raise ValueError(f"Unknown vote position {vote.vote}")

        return cls.model_construct(
            id=f"uk.org.publicwhip/person/{vote.person_id}", option=option
        )


class VoteEvent(BaseModel):
    counts: list[PopoloVoteCount]
    votes: list[PopoloVote]


class PopoloMotion(BaseModel):
    id: str
    organization_id: str
    policy_vote: PopoloVoteType
    text: str
    date: date
    vote_events: list[VoteEvent]


class PopoloSource(BaseModel):
    url: str


class PopoloAspect(BaseModel):
    """
    Aspects are associated votes
    """

    source: str
    direction: PopoloDirection
    motion: PopoloMotion


def pw_style_motion_description(
    motion_passed: int, direction: PolicyDirection, strength: PolicyStrength
) -> PopoloDirection:
    if motion_passed:
        # aye is the same as majority
        # no is the same as minority
        if direction == PolicyDirection.AGREE:
            if strength == PolicyStrength.STRONG:
                return PopoloDirection.MAJORITY_STRONG
            elif strength == PolicyStrength.WEAK:
                return PopoloDirection.MAJORITY_WEAK
        elif direction == PolicyDirection.AGAINST:
            if strength == PolicyStrength.STRONG:
                return PopoloDirection.MINORITY_STRONG
            elif strength == PolicyStrength.WEAK:
                return PopoloDirection.MINORITY_WEAK
    else:
        # aye is the same as minority
        # no is the same as majority
        if direction == PolicyDirection.AGREE:
            if strength == PolicyStrength.STRONG:
                return PopoloDirection.MINORITY_STRONG
            elif strength == PolicyStrength.WEAK:
                return PopoloDirection.MINORITY_WEAK
        elif direction == PolicyDirection.AGAINST:
            if strength == PolicyStrength.STRONG:
                return PopoloDirection.MAJORITY_STRONG
            elif strength == PolicyStrength.WEAK:
                return PopoloDirection.MAJORITY_WEAK
    # other option is that this was a abstain vote in pw
    # which in the long run we want want rid of
    return PopoloDirection.ABSTAIN


def org_type(chamber: Chamber) -> ValidOrganizationType:
    match chamber.slug:
        case ChamberSlug.COMMONS:
            return ValidOrganizationType.COMMONS
        case ChamberSlug.LORDS:
            return ValidOrganizationType.LORDS
        case ChamberSlug.SCOTLAND:
            return ValidOrganizationType.SCOTTISH_PARLIAMENT
        case _:
            raise ValueError(f"Unknown chamber {chamber.slug}")


def breakdown_to_vote_count(
    overall_breakdown: DivisionBreakdown,
) -> list[PopoloVoteCount]:
    return [
        PopoloVoteCount(
            option=PopoloVoteOption.NO, value=overall_breakdown.against_motion
        ),
        PopoloVoteCount(
            option=PopoloVoteOption.AYE, value=overall_breakdown.for_motion
        ),
        PopoloVoteCount(
            option=PopoloVoteOption.BOTH, value=overall_breakdown.neutral_motion
        ),
        PopoloVoteCount(
            option=PopoloVoteOption.ABSENT, value=overall_breakdown.absent_motion
        ),
    ]


def get_division_url(div: Division, policy_id: int) -> str:
    template = "http://www.publicwhip.org.uk/division.php?date={date}&number={number}&dmp={policy_id}&house=commons&display=allpossible"
    return template.format(
        date=div.date.strftime("%Y-%m-%d"),
        number=div.division_number,
        policy_id=policy_id,
    )


class PairedPolicy(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    policy: Policy
    own_distribution: VoteDistribution
    other_distribution: VoteDistribution


class PopoloPolicy(BaseModel):
    title: str
    text: str
    sources: PopoloSource
    aspects: list[PopoloAspect]
    # alignments isn't in original, but brings in the XML data
    alignments: list[ReducedPersonPolicyLink]

    @classmethod
    def from_policy_id(cls, policy_id: int):
        """
        Create a replacement object for the https://www.publicwhip.org.uk/data/popolo/363.json
        view
        """
        policy = Policy.objects.get(id=policy_id)

        # just refer back to public whip for moment as we're not public
        url = f"https://www.publicwhip.org.uk/policy.php?id={policy_id}"

        aspects = []
        for link in policy.division_links.all().prefetch_related(
            "decision", "decision__votes", "decision__overall_breakdowns"
        ):
            # for the moment, we only care about the commons
            if link.decision.chamber.slug != ChamberSlug.COMMONS:
                continue
            division = link.decision
            strength = link.strength
            id = (
                f"pw-{division.date}-{division.division_number}-{division.chamber.slug}"
            )
            overall_breakdown = link.decision.overall_breakdowns.all()[0]
            motion_result = overall_breakdown.motion_result_int
            motion_desc = pw_style_motion_description(
                motion_result, link.alignment, strength
            )
            motion_org = org_type(division.chamber)
            counts = breakdown_to_vote_count(overall_breakdown)
            # turn off pydantic validation for a big speed boost here
            votes = [
                PopoloVote.from_vote_unvalidated(v) for v in link.decision.votes.all()
            ]
            vote_events = VoteEvent(counts=counts, votes=votes)
            division_url = get_division_url(division, policy_id)
            motion = PopoloMotion(
                id=id,
                policy_vote=PopoloVoteType.from_modern(link.alignment, link.strength),
                organization_id=motion_org,
                text=division.division_name,
                date=division.date,
                vote_events=[vote_events],
            )
            aspect = PopoloAspect(
                source=division_url, direction=motion_desc, motion=motion
            )
            aspects.append(aspect)

        reduced_alignments = []

        paired_distributions = PairedPersonDistributions.from_distributions(
            list(policy.vote_distributions.filter(period__slug="ALL_TIME"))
        )

        for pair in paired_distributions:
            absent = (
                pair.own_distribution.num_votes_absent
                + pair.own_distribution.num_strong_votes_absent
            )

            both_voted = (
                pair.own_distribution.total_votes
                - pair.own_distribution.num_votes_abstain
                - pair.own_distribution.num_strong_votes_abstain
                - absent
            )
            link = None

            if policy.id is None:
                raise ValueError("Policy id is None")

            party = pair.own_distribution.party
            party_slug = party.slug if party else "none"

            item = ReducedPersonPolicyLink(
                person_id=pair.person.str_id(),
                policy_id=policy.id,
                comparison_period=pair.period,
                comparison_party=party_slug,
                chamber=ChamberSlug.COMMONS,
                count_present=int(both_voted),
                count_absent=int(absent),
                start_year=int(pair.own_distribution.start_year),
                end_year=int(pair.own_distribution.end_year),
                no_party_comparison=pair.no_party_comparison,
                person_distance_from_policy=pair.own_distribution.distance_score,
                comparison_distance_from_policy=pair.other_distribution.distance_score,
                comparison_score_diff=pair.comparison_score_difference,
            )

            reduced_alignments.append(item)

        policy = PopoloPolicy(
            title=policy.name,
            text=policy.policy_description,
            sources=PopoloSource(url=url),
            aspects=aspects,
            alignments=reduced_alignments,
        )

        return policy
