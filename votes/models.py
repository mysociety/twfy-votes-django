from __future__ import annotations

import datetime
import html
from dataclasses import dataclass
from itertools import groupby
from typing import (
    TYPE_CHECKING,
    Any,
    NotRequired,
    Optional,
    Protocol,
    Self,
    Type,
    TypedDict,
    TypeVar,
    cast,
)

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

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
    JSONField,
    ManyToMany,
    OptionalDateTimeField,
    PrimaryKey,
    TextField,
    field,
    related_name,
)

from .consts import (
    ChamberSlug,
    EvidenceType,
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
    WhipDirection,
    WhipPriority,
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


class UserPersonLink(DjangoVoteModel):
    """
    For connecting users to specific people
    Used to give reps the ability to add content
    related to them.
    """

    user: DoNothingForeignKey[User] = related_name("user_person_links")
    user_id: Dummy[int] = 0
    person: DoNothingForeignKey[Person] = related_name("user_person_links")
    person_id: Dummy[int] = 0


class InstructionDict(TypedDict):
    model: NotRequired[str]
    group: NotRequired[str]
    start_group: NotRequired[str]
    end_group: NotRequired[str]
    all: NotRequired[bool]
    quiet: NotRequired[bool]
    update_since: NotRequired[datetime.date]
    update_last: NotRequired[int]


@dataclass
class UrlColumn:
    url: str
    text: str

    def __str__(self) -> str:
        return f'<a href="{self.url}">{self.text}</a>'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UrlColumn):
            return NotImplemented
        return self.text == other.text

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, UrlColumn):
            return NotImplemented
        return self.text < other.text

    def __le__(self, other: object) -> bool:
        if not isinstance(other, UrlColumn):
            return NotImplemented
        return self.text <= other.text

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, UrlColumn):
            return NotImplemented
        return self.text > other.text

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, UrlColumn):
            return NotImplemented
        return self.text >= other.text


class DecisionTag(DjangoVoteModel):
    """
    A tag that can be applied to a decision
    """

    tag_type: TagType
    slug: str
    name: str
    desc: TextField = ""
    extra_data: JSONField = field(default=dict)
    agreements: DummyManyToMany[Agreement] = related_name("tags")
    divisions: DummyManyToMany[Division] = related_name("tags")

    def desc_markdown(self):
        """
        Convert the description to HTML
        """
        lines = self.desc.split("\n")
        text = "\n\n\n".join([x.strip() for x in lines]).strip()

        return markdown.markdown(text, extensions=["tables"])

    def url(self):
        return reverse("tag", args=[self.tag_type, self.slug])

    def get_decisions(self):
        return list(
            self.agreements.all().prefetch_related("tags", "chamber", "motion")
        ) + list(self.divisions.all().prefetch_related("tags", "chamber", "motion"))

    def decisions_df_by_chamber(self) -> dict[Chamber, pd.DataFrame]:
        """
        Get a dataframe of decisions by chamber
        """

        data = self.decisions_df()

        # group by chamber
        chambers = {}
        for chamber, df in data.groupby("Chamber"):
            chambers[chamber] = df

        return chambers

    def decisions_df(self) -> pd.DataFrame:
        ao_override = AnalysisOverride.bulk_lookup()

        def get_voting_cluster(item: Division | Agreement) -> dict[str, str]:
            if isinstance(item, Agreement):
                return item.voting_cluster()
            elif isinstance(item, Division) and item.id:
                return item.voting_cluster(override_lookup=ao_override)
            else:
                return {"cluster_name": "Unknown", "desc": ""}

        data = [
            {
                "Chamber": d.chamber,
                "Date": d.date,
                "Decision": UrlColumn(url=d.url(), text=d.safe_decision_name()),
                "Vote Type": d.decision_type,
                "Motion Type": MotionType(d.motion_type()).display_name(),
                "Voting Cluster": get_voting_cluster(d)["cluster_name"],
            }
            for d in self.get_decisions()
        ]

        df = pd.DataFrame(data=data)
        df = df.sort_values("Date", ascending=False)
        return df


class BaseTagLink(DjangoVoteModel, abstract=True):
    tag: DoNothingForeignKey[DecisionTag] = related_name("decision_tag_links")
    tag_id: Dummy[int] = 0
    extra_data: JSONField = field(default=dict)

    @property
    def decision_id(self) -> int:
        raise NotImplementedError

    @classmethod
    def sync_tags(
        cls,
        links: list[Self],
        *,
        quiet: bool = False,
        clear_absent: bool = True,
    ):
        """
        Sync the tags for a set of links.
        This will remove any existing links and add the new ones
        """

        links.sort(key=lambda x: x.tag_id)

        for tag_id, tag_links in groupby(links, key=lambda x: x.tag_id):
            tag_links = list(tag_links)
            tag = tag_links[0].tag
            cls.sync_tag(tag, tag_links, quiet=quiet, clear_absent=clear_absent)

    @classmethod
    def sync_tag(
        cls,
        tag: DecisionTag,
        links: list[Self],
        *,
        quiet: bool = False,
        clear_absent: bool = True,
    ):
        tag_ids = [x.tag_id for x in links]
        if not all(x == tag.id for x in tag_ids):
            raise ValueError("All links must be for the same tag")

        # remove any existing links
        existing_id_lookup = {x.decision_id: x.id for x in cls.objects.filter(tag=tag)}

        decision_ids = [link.decision_id for link in links]

        existing_ids = existing_id_lookup.keys()
        to_remove = set(existing_ids) - set(decision_ids)
        to_add = set(decision_ids) - set(existing_ids)
        to_edit = set(decision_ids) & set(existing_ids)

        if to_remove and clear_absent:
            if not quiet:
                print(f"Removing {len(to_remove)} links for tag {tag.slug}")
            # if cls is AgreementTagLink, then we need to remove the links
            if issubclass(cls, AgreementTagLink):
                cls.objects.filter(tag=tag, agreement_id__in=to_remove).delete()
            elif issubclass(cls, DivisionTagLink):
                cls.objects.filter(tag=tag, division_id__in=to_remove).delete()

        if to_add:
            if not quiet:
                print(f"Adding {len(to_add)} links for tag {tag.slug}")
            to_create = [x for x in links if x.decision_id in to_add]
            cls.objects.bulk_create(to_create)  # type: ignore

        if to_edit:
            if not quiet:
                print(f"Editing {len(to_edit)} links for tag {tag.slug}")
            edit_objects = [x for x in links if x.decision_id in to_edit]
            for e in edit_objects:
                e.id = existing_id_lookup[e.decision_id]
            cls.objects.bulk_update(
                edit_objects,  # type: ignore
                ["extra_data"],
            )


class DivisionTagLink(BaseTagLink):
    """
    A link between a division and a tag
    """

    tag: DoNothingForeignKey[DecisionTag] = related_name("division_tag_links")
    division: DoNothingForeignKey[Division] = related_name("tag_links")
    division_id: Dummy[int] = 0

    @property
    def decision_id(self) -> int:
        return self.division_id

    @classmethod
    def sync_tag_from_division_id_list(
        cls,
        tag: DecisionTag,
        division_ids: list[int],
        *,
        quiet: bool = False,
        clear_absent: bool = True,
    ):
        """
        Sync the tags for a set of links.
        This will remove any existing links and add the new ones
        """

        links = [
            cls(tag=tag, division_id=x, extra_data={})
            for x in division_ids
            if x is not None
        ]
        cls.sync_tags(links, quiet=quiet, clear_absent=clear_absent)


class AgreementTagLink(BaseTagLink):
    """
    A link between an agreement and a tag
    """

    tag: DoNothingForeignKey[DecisionTag] = related_name("agreement_tag_links")
    agreement: DoNothingForeignKey[Agreement] = related_name("tag_links")
    agreement_id: Dummy[int] = 0

    @property
    def decision_id(self) -> int:
        return self.agreement_id

    @classmethod
    def sync_tag_from_agreement_id_list(
        cls,
        tag: DecisionTag,
        division_ids: list[int],
        *,
        quiet: bool = False,
        clear_absent: bool = True,
    ):
        """
        Sync the tags for a set of links.
        This will remove any existing links and add the new ones
        """

        links = [
            cls(tag=tag, agreement_id=x, extra_data={})
            for x in division_ids
            if x is not None
        ]
        cls.sync_tags(links, quiet=quiet, clear_absent=clear_absent)


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

    def decision_number_or_ref(self) -> str: ...

    def legislation_tag(self) -> DecisionTag | None: ...


DecisionProtocolType = TypeVar("DecisionProtocolType", bound=DecisionProtocol)


def is_valid_decision_model(
    klass: Type[DecisionProtocolType],
) -> Type[DecisionProtocolType]:
    return klass


@dataclass
class DistributionGroup:
    party: Organization | None
    chamber: Chamber
    period: PolicyComparisonPeriod

    def key(self):
        party_id = self.party.id if self.party else "independent"
        return f"{party_id}-{self.chamber.id}-{self.period.id}"

    def party_slug(self):
        if self.party:
            return self.party.slug
        return "independent"

    def party_name(self):
        if self.party:
            return self.party.name
        return "Independent"


class Update(DjangoVoteModel):
    """
    Update queue model
    """

    id: PrimaryKey = None
    date_created: OptionalDateTimeField
    date_started: OptionalDateTimeField
    date_completed: OptionalDateTimeField
    failed: bool = False
    error_message: TextField = ""
    instructions: dict
    created_via: str

    @classmethod
    def create_task(
        cls, instructions: dict, created_via: str, check_for_running: bool = True
    ):
        if check_for_running:
            # basic check that we don't have the same instructions running or queued to be started
            currently_running = cls.created_not_finished(last_hour=True)
            for update in currently_running:
                if update.instructions == instructions:
                    return update

        return cls.objects.create(
            instructions=instructions,
            created_via=created_via,
            date_created=timezone.now(),
        )

    def start(self):
        self.date_started = timezone.now()
        self.save()

    def complete(self):
        self.date_completed = timezone.now()
        self.error_message = ""
        self.save()

    def fail(self, error_message: str):
        self.date_completed = timezone.now()
        self.failed = True
        self.error_message = error_message
        self.save()

    def check_similar_in_progress(self):
        return (
            Update.objects.filter(
                date_completed=None,
                instructions=self.instructions,
                date_created__gte=timezone.now() - datetime.timedelta(hours=1),
            )
            .exclude(id=self.id)
            .exists()
        )

    @classmethod
    def to_run(cls):
        """
        Get a set of updates to run
        Also de-duplicates if multiple instructions are the same
        """
        items = cls.objects.filter(date_completed=None, date_started=None)
        # remove duplicate instructions in a single run
        instructions = []
        final_items = []
        for item in items:
            if item.instructions in instructions:
                item.delete()
            else:
                instructions.append(item.instructions)
                final_items.append(item)
        return final_items

    @classmethod
    def created_not_finished(cls, last_hour: bool = False):
        if last_hour:
            # get all items created in the last hour
            return cls.objects.filter(
                date_created__gte=timezone.now() - datetime.timedelta(hours=1),
                date_completed=None,
            )
        return cls.objects.filter(date_completed=None)


class Person(DjangoVoteModel):
    id: PrimaryKey = None
    name: str
    memberships: DummyOneToMany["Membership"] = related_name("person")
    votes: DummyOneToMany[Vote] = related_name("person")
    vote_distributions: DummyOneToMany[VoteDistribution] = related_name("person")
    rebellion_rates: DummyOneToMany[RebellionRate] = related_name("person")

    class Meta:
        ordering = ["name"]

    def str_id(self):
        return f"uk.org.publicwhip/person/{self.id}"

    def url(self) -> str:
        return reverse("person", args=[self.id])

    def votes_url(self, year: str = "all"):
        return reverse("person_votes", kwargs={"person_id": self.id, "year": year})

    def recent_years_with_votes(self):
        items = (
            self.rebellion_rates.filter(period_type=RebellionPeriodType.YEAR)
            .order_by("-period_number")
            .values_list("period_number", flat=True)
        )
        return [str(x) for x in items]

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

    @classmethod
    def current_in_chamber(cls, chamber_slug: ChamberSlug):
        memberships = Membership.objects.filter(
            chamber_slug=chamber_slug, end_date__gte=datetime.date.today()
        )
        return cls.objects.filter(memberships__in=memberships)

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

        votes_query = votes_query.prefetch_related("division", "division__motion")

        data = [
            {
                "Date": v.division.date,
                "Division": UrlColumn(
                    url=v.division.url(), text=v.division.safe_decision_name()
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

    def __str__(self) -> str:
        return self.name


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

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Chamber):
            return NotImplemented
        return self.slug == other.slug

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Chamber):
            return NotImplemented
        return self.slug < other.slug

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Chamber):
            return NotImplemented
        return self.slug <= other.slug

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Chamber):
            return NotImplemented
        return self.slug > other.slug

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Chamber):
            return NotImplemented
        return self.slug >= other.slug

    def __hash__(self) -> int:
        return hash(self.slug)

    def member_singular(self) -> str:
        return self.member_plural[:-1]

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
        return sorted(list(set(years)))

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

    def verison_agnostic_gid_match(self, banned_ids: list[str]) -> bool:
        def version_agnostic_gid(gid: str) -> str:
            """
            Reduce 2020-01-01b, 2020-01-01c to 2020-01-01
            """
            parts = gid.split("/")
            date = parts.pop(-1)
            if date[10] != ".":
                date = date[:10] + date[11:]

            return "/".join(parts + [date])

        self_gid = version_agnostic_gid(self.gid)
        for banned_id in banned_ids:
            if self_gid == version_agnostic_gid(banned_id):
                return True
        return False

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

        text = html.unescape(text)

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
    whip_reports: DummyOneToMany[WhipReport] = related_name("division")
    division_annotations: DummyOneToMany[DivisionAnnotation] = related_name("division")
    vote_annotations: DummyOneToMany[VoteAnnotation] = related_name("division")
    tags: DummyManyToMany[DecisionTag] = field(
        models.ManyToManyField,
        to=DecisionTag,
        related_name="divisions",
        through=DivisionTagLink,
        through_fields=("division", "tag"),
        default=None,
    )
    motion_id: Dummy[Optional[int]] = None
    motion: Optional[Motion] = field(
        models.ForeignKey,
        to=Motion,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        default=None,
        related_name="divisions",
    )

    def first_breakdown(self):
        """
        This doesn't use the 'first' because it's been prefetched.
        And that generates another query.
        """
        return self.overall_breakdowns.all()[0]

    def decision_number_or_ref(self) -> str:
        return str(self.division_number)

    def whip_report_df(self) -> pd.DataFrame | None:
        wf = list(
            self.whip_reports.all().values(
                "party__name", "whip_direction", "whip_priority"
            )
        )
        if not wf:
            return None
        df = pd.DataFrame(data=wf)
        df.columns = ["Party", "Whip direction", "Whip priority"]
        # remove duplicates
        df = df.drop_duplicates()
        return df

    def get_annotations(self) -> list[DivisionAnnotation]:
        return list(self.division_annotations.all())

    def analysis_override(
        self, override_lookup: dict[str, AnalysisOverride] | None = None
    ) -> Optional[AnalysisOverride]:
        if override_lookup is not None:
            return override_lookup.get(self.key)
        existing = getattr(self, "_override", None)
        if existing:
            return existing
        result = AnalysisOverride.objects.filter(decision_key=self.key).first()
        setattr(self, "_override", result)
        return result

    def apply_analysis_override(self):
        override = self.analysis_override()
        if not override:
            return self
        if override.banned_motion_ids:
            banned_ids = [x for x in override.banned_motion_ids.split(",")]
            if self.motion:
                if self.motion.verison_agnostic_gid_match(banned_ids):
                    self.motion = None

        return self

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
        ob_list = list(self.overall_breakdowns.all())
        if len(ob_list) == 1:
            ob = ob_list[0]
        else:
            ob = None
        if ob:
            return ob
        raise ValueError("No overall breakdown found")

    def legislation_tag(self) -> DecisionTag | None:
        tag = list([x for x in self.tags.all() if x.tag_type == TagType.LEGISLATION])
        if tag:
            tag = tag[0]
        else:
            tag = None
        return tag

    def voting_cluster(
        self,
        override_lookup: dict[str, AnalysisOverride] | None = None,
    ) -> dict[str, Any]:
        tag = list([x for x in self.tags.all() if x.tag_type == TagType.GOV_CLUSTERS])
        if tag:
            tag = tag[0]
        else:
            tag = None

        cluster_name = tag.name if tag else "Unknown"

        if cluster_name.endswith("_outlier"):
            is_outlier = True
        else:
            is_outlier = False

        bespoke = ""

        analysis_override = self.analysis_override(override_lookup)
        if analysis_override:
            if analysis_override.parl_dynamics_group:
                cluster_name = analysis_override.parl_dynamics_group
            if analysis_override.manual_parl_dynamics_desc:
                bespoke = analysis_override.manual_parl_dynamics_desc

        desc = tag.desc_markdown() if tag else ""

        return {
            "tag": cluster_name,
            "cluster_name": cluster_name,
            "desc": desc,
            "bespoke": bespoke,
            "is_outlier": is_outlier,
        }

    def gid(self) -> str:
        gid = self.source_gid.split("/")[-1]
        if not gid:
            return ""
        return gid

    def twfy_link(self) -> str:
        return self.chamber.twfy_debate_link(self.gid())

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
        if self.motion and self.chamber_slug == ChamberSlug.SCOTLAND:
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
                "Tellers": x.teller_for_motion + x.teller_against_motion,
                "Party turnout": x.signed_votes / x.vote_participant_count,
                "For motion percentage": (
                    x.for_motion_percentage
                    if not pd.isna(x.for_motion_percentage)
                    else "n/a"
                ),
            }
            for x in self.party_breakdowns.all().prefetch_related("party")
        ]

        df = pd.DataFrame(data=data)

        remove_if_all_zero = ["Tellers", "Neutral motion"]

        for col in remove_if_all_zero:
            if col in df.columns and df[col].sum() == 0:
                df = df.drop(columns=[col])

        # drop tellers for now
        if "Tellers" in df.columns:
            df = df.drop(columns=["Tellers"])

        return df

    def overall_breakdown_df(self) -> pd.DataFrame:
        overall_breakdown = self.overall_breakdowns.first()
        if overall_breakdown is None:
            raise ValueError("No overall breakdown found")

        overall_breakdown = cast(DivisionBreakdown, overall_breakdown)

        overall_breakdown_dict = {
            "Grouping": f"All {self.chamber.member_plural}",
            f"{self.chamber.member_plural} on date": overall_breakdown.vote_participant_count,
            "Vote participant count": overall_breakdown.signed_votes,
            "For motion": overall_breakdown.for_motion,
            "Against motion": overall_breakdown.against_motion,
            "Neutral motion": overall_breakdown.neutral_motion,
            "Absent motion": overall_breakdown.absent_motion,
            "Tellers": overall_breakdown.teller_for_motion
            + overall_breakdown.teller_against_motion,
            "Turnout": overall_breakdown.signed_votes
            / overall_breakdown.vote_participant_count,
            "For motion percentage": overall_breakdown.for_motion_percentage,
        }

        all_breakdowns = [overall_breakdown_dict]
        all_breakdowns = [dict(x) for x in all_breakdowns]
        df = pd.DataFrame(data=all_breakdowns)

        remove_if_all_zero = ["Tellers", "Neutral motion"]

        for col in remove_if_all_zero:
            if col in df.columns and df[col].sum() == 0:
                df = df.drop(columns=[col])

        # drop tellers for now
        if "Tellers" in df.columns:
            df = df.drop(columns=["Tellers"])

        return df

    def gov_breakdown_df(self) -> pd.DataFrame:
        gov_breakdowns = [
            {
                "Grouping": "Government" if x.is_gov else "Opposition",
                f"{self.chamber.member_plural} on date": x.vote_participant_count,
                "Vote participant count": x.signed_votes,
                "For motion": x.for_motion,
                "Against motion": x.against_motion,
                "Neutral motion": x.neutral_motion,
                "Absent motion": x.absent_motion,
                "Tellers": x.teller_for_motion + x.teller_against_motion,
                "Turnout": x.signed_votes / x.vote_participant_count,
                "For motion percentage": x.for_motion_percentage,
            }
            for x in self.is_gov_breakdowns.all()
        ]

        all_breakdowns = [dict(x) for x in gov_breakdowns]
        df = pd.DataFrame(data=all_breakdowns)

        remove_if_all_zero = ["Tellers", "Neutral motion"]

        for col in remove_if_all_zero:
            if col in df.columns and df[col].sum() == 0:
                df = df.drop(columns=[col])

        # drop tellers for now
        if "Tellers" in df.columns:
            df = df.drop(columns=["Tellers"])

        return df

    def vote_groups(self):
        vote_groups = {
            "directional": [],
            "tellers": [],
            "misc": [],
        }

        sdf = self.votes_df().sort_values("Person").sort_values("Party")

        for group, df in sdf.groupby("Vote"):
            if group == "Absent":
                pass
            if group == "Tellaye":
                group = "Aye (Teller)"
            if group == "Tellno":
                group = "No (Teller)"
            vote_group = {
                "grouping": group,
                "count": len(df),
                "members": df.to_dict(orient="records"),
            }
            match group:
                case "Aye" | "No":
                    vote_groups["directional"].append(vote_group)
                case "Absent" | "Abstain":
                    vote_groups["misc"].append(vote_group)
                case "Aye (Teller)" | "No (Teller)":
                    vote_groups["tellers"].append(vote_group)

        return vote_groups

    def votes_df(self) -> pd.DataFrame:
        existing = getattr(self, "_votes_df", None)
        if existing is not None:
            return existing

        relevant_memberships = Membership.objects.filter(
            chamber=self.chamber, start_date__lte=self.date, end_date__gte=self.date
        ).prefetch_related("party", "person")
        person_to_membership_map = {x.person_id: x for x in relevant_memberships}

        vote_annotations = self.vote_annotations.all()
        vote_annotation_map = {x.person_id: x.url_column() for x in vote_annotations}

        data = [
            {
                "Person": UrlColumn(url=v.person.url(), text=v.person.name),
                "Party": person_to_membership_map[v.person_id].party.name,
                "Vote": v.vote_desc(),
                "Party alignment": 1
                - (
                    v.diff_from_party_average
                    if v.diff_from_party_average is not None
                    else nan
                ),
                "Annotation": vote_annotation_map.get(v.person_id, "-"),
            }
            for v in self.votes.all().prefetch_related("person")
        ]

        for d in data:
            if pd.isna(d["Party alignment"]):
                d["Party alignment"] = "n/a"

        df = pd.DataFrame(data=data)

        if len(vote_annotation_map) == 0 and "Annotation" in df.columns:
            df = df.drop(columns=["Annotation"])

        setattr(self, "_votes_df", df)

        return df


class DivisionBreakdown(DjangoVoteModel):
    division_id: Dummy[int]
    division: DoNothingForeignKey[Division] = related_name("overall_breakdowns")
    vote_participant_count: int
    total_possible_members: int
    for_motion: int
    against_motion: int
    neutral_motion: int
    teller_for_motion: int
    teller_against_motion: int
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
    teller_for_motion: int
    teller_against_motion: int
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
    teller_for_motion: int
    teller_against_motion: int
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
        # not sure why this is needed, but coming back as string
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
    negative: bool
    motion_id: Dummy[Optional[int]] = None
    motion: Optional[Motion] = field(
        models.ForeignKey,
        to=Motion,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        related_name="agreements",
        default=None,
    )
    agreement_annotations: DummyOneToMany[AgreementAnnotation] = related_name(
        "agreement"
    )
    tags: DummyManyToMany[DecisionTag] = field(
        models.ManyToManyField,
        to=DecisionTag,
        related_name="agreements",
        through=AgreementTagLink,
        through_fields=("agreement", "tag"),
        default=None,
    )

    def legislation_tag(self) -> DecisionTag | None:
        tag = list([x for x in self.tags.all() if x.tag_type == TagType.LEGISLATION])
        if tag:
            tag = tag[0]
        else:
            tag = None
        return tag

    def decision_number_or_ref(self) -> str:
        return str(self.decision_ref)

    def get_annotations(self) -> list[AgreementAnnotation]:
        return list(self.agreement_annotations.all())

    def analysis_override(self) -> Optional[AnalysisOverride]:
        existing = getattr(self, "_override", None)
        if existing:
            return existing
        result = AnalysisOverride.objects.filter(decision_key=self.key).first()
        setattr(self, "_override", result)
        return result

    def apply_analysis_override(self):
        override = self.analysis_override()
        if not override:
            return self
        if override.banned_motion_ids:
            banned_ids = [x for x in override.banned_motion_ids.split(",")]
            if self.motion:
                if self.motion.gid in banned_ids:
                    self.motion = None

        return self

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
        return {"tag": "Agreement", "cluster_name": "Agreement"}

    def safe_decision_name(self) -> str:
        return self.decision_name or "[missing title]"

    def gid(self) -> str:
        gid = self.decision_ref.split("/")[-1]
        # remove the final .number
        gid = ".".join(gid.split(".")[:-1])
        # if first character is a digit, prepend a dot
        if gid[0].isdigit():
            gid = f".{gid}"
        gid = f"{self.date.isoformat()}{gid}"
        return gid

    def twfy_link(self) -> str:
        return self.chamber.twfy_debate_link(self.gid())

    def votes_df(self) -> pd.DataFrame:
        relevant_memberships = Membership.objects.filter(
            chamber=self.chamber, start_date__lte=self.date, end_date__gte=self.date
        ).prefetch_related("person", "party")
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

        ao_override = AnalysisOverride.bulk_lookup()

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
                "voting cluster": x.decision.voting_cluster(
                    override_lookup=ao_override,
                )["cluster_name"],
                "participant count": x.decision.single_breakdown().signed_votes,
            }
            for x in self.division_links.all().prefetch_related(
                "decision",
                "decision__tags",
                "decision__overall_breakdowns",
                "decision__motion",
            )
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
                "voting cluster": x.decision.voting_cluster()["cluster_name"],
                "participant count": 0,
            }
            for x in self.agreement_links.all().prefetch_related("decision")
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
    def str_similarity_percentage(self) -> str:
        return f"{round((1 - self.distance_score) * 100)}%"

    @property
    def str_distance_percentage(self) -> str:
        return f"{round((self.distance_score) * 100)}%"

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


class WhipReport(DjangoVoteModel):
    division_id: Dummy[int] = 0
    division: DoNothingForeignKey[Division] = related_name("whip_reports")
    party_id: Dummy[int] = 0
    party: DoNothingForeignKey[Organization] = related_name("whip_reports")
    whip_direction: WhipDirection
    whip_priority: WhipPriority
    evidence_type: EvidenceType
    evidence_detail: TextField = field(default="", blank=True)


class DivisionAnnotation(DjangoVoteModel):
    division_id: Dummy[int] = 0
    division: DoNothingForeignKey[Division] = related_name("division_annotations")
    detail: str = ""
    link: str = ""

    def html(self) -> str:
        if self.detail and self.link:
            return f"<a href='{self.link}'>{self.detail}</a>"
        if self.link:
            return f"<a href='{self.link}'>{self.link}</a>"
        return self.detail


class AgreementAnnotation(DjangoVoteModel):
    agreement_id: Dummy[int] = 0
    agreement: DoNothingForeignKey[Agreement] = related_name("agreement_annotations")
    detail: str = ""
    link: str = ""

    def html(self) -> str:
        if self.detail and self.link:
            return f"<a href='{self.link}'>{self.detail}</a>"
        if self.link:
            return f"<a href='{self.link}'>{self.link}</a>"
        return self.detail


class VoteAnnotation(DjangoVoteModel):
    division_id: Dummy[int] = 0
    division: DoNothingForeignKey[Division] = related_name("vote_annotations")
    person_id: Dummy[int] = 0
    person: DoNothingForeignKey[Person] = related_name("vote_annotations")
    detail: str = ""
    link: str

    def html(self) -> str:
        if self.detail and self.link:
            return f"<a href='{self.link}'>{self.detail}</a>"
        if self.link:
            return f"<a href='{self.link}'>{self.link}</a>"
        return self.detail

    def url_column(self) -> UrlColumn:
        return UrlColumn(url=self.link, text=self.detail)


class AnalysisOverride(DjangoVoteModel):
    """
    This is an option to override automatically created division data.
    """

    decision_key: str
    banned_motion_ids: TextField = field(blank=True, default="")
    parl_dynamics_group: str = field(blank=True, default="")
    manual_parl_dynamics_desc: TextField = field(blank=True, default="")

    @classmethod
    def bulk_lookup(cls) -> dict[str, AnalysisOverride]:
        return {x.decision_key: x for x in cls.objects.all()}
