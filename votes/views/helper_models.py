from __future__ import annotations

import datetime
from itertools import groupby

from django.urls import reverse

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, computed_field

from twfy_votes.helpers.routes import RouteApp

from ..consts import (
    IssueType,
    MotionType,
    PolicyGroupSlug,
    PolicyStatus,
    PolicyStrength,
    PowersAnalysis,
)
from ..models import (
    Agreement,
    Chamber,
    Division,
    Person,
    Policy,
    PolicyDivisionLink,
    PolicyGroup,
    UrlColumn,
    VoteDistribution,
)

app = RouteApp(app_name="votes")


class DivisionSearch(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    start_date: datetime.date
    end_date: datetime.date
    chamber: Chamber
    decisions: list[Division | Agreement]

    def decisions_df(self) -> pd.DataFrame:
        data = [
            {
                "Date": d.date,
                "Division": UrlColumn(url=d.url(), text=d.safe_decision_name()),
                "Vote Type": d.decision_type,
                "Motion Type": MotionType(d.motion_type()).display_name(),
                "Uses Parl. Powers": d.motion_uses_powers.simple_str(),
                "Voting Cluster": d.voting_cluster()["desc"],
            }
            for d in self.decisions
        ]

        return pd.DataFrame(data=data)


class ChamberPolicyGroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    slug: str
    policies: list[Policy]


class PolicyCollection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    groups: list[PolicyDisplayGroup]

    def __iter__(self):
        return iter(self.groups)

    @classmethod
    def from_distributions(
        cls, distributions: list[VoteDistribution], url_base: list[str | int]
    ) -> list[PolicyDisplayGroup]:
        def get_key(v: VoteDistribution) -> str:
            return (
                f"{v.policy_id}-{v.person_id}-{v.period_id}-{v.chamber_id}-{v.party_id}"
            )

        sorted_list = sorted(distributions, key=get_key)

        pp_list: list[PairedPolicy] = []

        for key, group in groupby(sorted_list, key=get_key):
            group = list(group)
            our_key = [x for x in group if x.is_target]
            their_key = [x for x in group if not x.is_target]
            if len(our_key) > 1 or len(their_key) > 1:
                raise ValueError("Too many distributions for the same policy")
            if len(our_key) == 0:
                # this may happen when someone has been present for agreements but not any votes
                # let's just skip this for the moment
                continue
                # raise ValueError(f"No distribution for the target for key : {key}")
            our_key = our_key[0]
            if len(their_key) == 0:
                their_key = our_key
            else:
                their_key = their_key[0]
            pp = PairedPolicy(
                policy=our_key.policy,
                own_distribution=our_key,
                other_distribution=their_key,
            )
            if our_key.distance_score == -1:
                # weed out no data avaliable policies
                continue
            pp_list.append(pp)

        groups: list[PolicyDisplayGroup] = []

        id_to_group_slug = {
            x.policy.id: [y.slug for y in x.policy.groups.all()] for x in pp_list
        }

        sig_links = [x for x in pp_list if x.significant_difference]
        groups.append(
            PolicyDisplayGroup(
                name="Significant Policies",
                slug="significant",
                paired_policies=sig_links,
                url_base=url_base,
            )
        )

        slug_lookup = {x.slug: x for x in PolicyGroup.objects.all()}

        for group_slug in PolicyGroupSlug:
            grouped_items = []
            for pp in pp_list:
                if group_slug in id_to_group_slug[pp.policy.id]:
                    grouped_items.append(pp)

            if len(grouped_items) > 0:
                groups.append(
                    PolicyDisplayGroup(
                        name=slug_lookup[group_slug].description,
                        slug=group_slug,
                        paired_policies=grouped_items,
                        url_base=url_base,
                    )
                )

        return groups


class PolicyDisplayGroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    slug: str
    url_base: list[str | int]
    paired_policies: list[PairedPolicy]

    def model_dump(self):
        return {
            "name": self.name,
            "paired_policies": [x.model_dump() for x in self.paired_policies],
        }

    def __iter__(self):
        return iter(self.paired_policies)

    def __len__(self):
        return len(self.paired_policies)

    def as_df(self) -> pd.DataFrame:
        class GroupTableItem(BaseModel):
            policy_name: str
            policy_status: str
            person_score: float
            person_score_verbose: str
            comparison_score: float
            diff: float
            sig_diff: bool

        items: list[GroupTableItem] = []
        for link in self.paired_policies:
            item_url = reverse(
                "person_policy_solo", args=self.url_base + [str(link.policy.id)]
            )
            item = GroupTableItem(
                policy_name=str(
                    UrlColumn(
                        # url=link.policy.url(), # link direct to policy item
                        url=item_url,
                        text=link.policy.context_description or link.policy.name,
                    )
                ),
                policy_status=link.policy.status,
                person_score=link.own_distribution.distance_score,
                person_score_verbose=link.own_distribution.verbose_score,
                comparison_score=link.other_distribution.distance_score,
                diff=link.comparison_score_difference,
                sig_diff=link.significant_difference,
            )
            items.append(item)

        df = pd.DataFrame(data=[x.model_dump() for x in items])

        return df


class PairedPersonDistributions(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    person: Person
    period: str
    own_distribution: VoteDistribution
    other_distribution: VoteDistribution
    no_party_comparison: bool = False

    @computed_field
    @property
    def comparison_score_difference(self) -> float:
        return (
            self.own_distribution.distance_score
            - self.other_distribution.distance_score
        )

    @classmethod
    def from_distributions(
        cls, distributions: list[VoteDistribution]
    ) -> list[PairedPersonDistributions]:
        def get_key(v: VoteDistribution) -> str:
            return (
                f"{v.policy_id}-{v.person_id}-{v.period_id}-{v.chamber_id}-{v.party_id}"
            )

        sorted_list = sorted(distributions, key=get_key)

        pp_list: list[PairedPersonDistributions] = []

        for key, group in groupby(sorted_list, key=get_key):
            group = list(group)
            our_key = [x for x in group if x.is_target]
            their_key = [x for x in group if not x.is_target]
            if len(our_key) > 1 or len(their_key) > 1:
                raise ValueError(
                    f"Too many distributions for the same policy, our_key: {our_key}, their_key: {their_key}"
                )
            if len(our_key) == 0:
                # this may happen when someone has been present for agreements but not any votes
                # let's just skip this for the moment
                continue
                # raise ValueError(f"No distribution for the target for key {key}")
            our_key = our_key[0]
            if len(their_key) == 0:
                no_party_comparison = True
                their_key = our_key
            else:
                no_party_comparison = False
                their_key = their_key[0]
            pp = PairedPersonDistributions(
                person=our_key.person,
                period=our_key.period.slug,
                own_distribution=our_key,
                other_distribution=their_key,
                no_party_comparison=no_party_comparison,
            )
            if our_key.distance_score == -1:
                # weed out no data avaliable policies
                continue
            pp_list.append(pp)

        return pp_list


class PairedPolicy(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    policy: Policy
    own_distribution: VoteDistribution
    other_distribution: VoteDistribution

    @computed_field
    @property
    def comparison_score_difference(self) -> float:
        return (
            self.own_distribution.distance_score
            - self.other_distribution.distance_score
        )

    @computed_field
    @property
    def significant_difference(self) -> bool:
        own_score = self.own_distribution.distance_score
        other_score = self.other_distribution.distance_score
        if own_score < 0.4 and other_score > 0.6:
            return True
        if own_score > 0.6 and other_score < 0.4:
            return True
        return False


class PolicyReport(BaseModel):
    """
    Catalog issues with a policy
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    policy: Policy
    division_issues: dict[IssueType, list[Division]] = Field(default_factory=dict)
    policy_issues: list[IssueType] = Field(default_factory=list)
    policy_warnings: list[IssueType] = Field(default_factory=list)

    def model_dump(self):
        from .api import DivisionSchema, PolicySchema

        data = {}
        data["policy"] = PolicySchema.from_orm(self.policy).model_dump()
        data["division_issues"] = {
            k.value: [DivisionSchema.from_orm(x).model_dump() for x in v]
            for k, v in self.division_issues.items()
        }
        data["policy_issues"] = [x.value for x in self.policy_issues]
        data["policy_warnings"] = [x.value for x in self.policy_warnings]

        return data

    def add_from_division_issue(
        self, division_link: PolicyDivisionLink, issue: IssueType
    ):
        """
        Add an issue to the list of issues for this division
        """
        ignore_format = f"ignore:{issue}"
        if ignore_format in division_link.notes:
            return False

        if issue not in self.division_issues:
            self.division_issues[issue] = []
        self.division_issues[issue].append(division_link.decision)
        return True

    def add_policy_issue(self, issue: IssueType, warning: bool = False):
        """
        Add an issue to the list of issues for this policy
        """
        ignore_format = f"ignore:{issue}"
        if ignore_format in self.policy.notes:
            return False

        if warning:
            if issue not in self.policy_warnings:
                self.policy_warnings.append(issue)
        else:
            if issue not in self.policy_issues:
                self.policy_issues.append(issue)
        return True

    def len_division_issues(self) -> int:
        return sum([len(x) for x in self.division_issues.values()])

    def has_issues(self) -> bool:
        return len(self.policy_issues) > 0 or len(self.division_issues) > 0

    def has_issues_or_warnings(self) -> bool:
        return (
            len(self.policy_issues) > 0
            or len(self.division_issues) > 0
            or len(self.policy_warnings) > 0
        )

    @classmethod
    def fetch_multiple(
        cls,
        statuses: list[PolicyStatus],
    ):
        """
        Run checks on policies.
        """

        policies = Policy.objects.filter(status__in=statuses).all()
        return [cls.from_policy(policy=policy) for policy in policies]

    @classmethod
    def from_policy(cls, policy: Policy) -> PolicyReport:
        """
        Score policy for identified issues
        """

        report = PolicyReport(policy=policy)
        strong_count = 0
        strong_without_power = 0
        for division in policy.division_links.all():
            # Test for overlap of strong votes and no powers
            uses_powers = (
                division.decision.motion_uses_powers == PowersAnalysis.USES_POWERS
            )
            if division.strength == PolicyStrength.STRONG:
                strong_count += 1
            if division.strength == PolicyStrength.STRONG:
                motion = division.decision.motion

                decision_type = motion.motion_type if motion else "Unknown"

                if (
                    "queen's speech" in division.decision.division_name.lower()
                    or decision_type == MotionType.GOVERNMENT_AGENDA
                ):
                    if report.add_from_division_issue(
                        division_link=division, issue=IssueType.STRONG_VOTE_GOV_AGENDA
                    ):
                        strong_without_power += 1

            # decisions before this date were cleared manually
            if (
                division.strength == PolicyStrength.STRONG
                and not uses_powers
                and division.decision.motion
            ):
                if report.add_from_division_issue(
                    division_link=division, issue=IssueType.STRONG_WITHOUT_POWER
                ):
                    strong_without_power += 1
            if (
                "opposition" in division.decision.division_name.lower()
                and division.strength == PolicyStrength.STRONG
            ):
                report.add_from_division_issue(
                    division_link=division, issue=IssueType.STRONG_WITHOUT_POWER
                )
        if strong_count == 0:
            report.add_policy_issue(issue=IssueType.NO_STRONG_VOTES)
        elif strong_count - strong_without_power == 0:
            report.add_policy_issue(issue=IssueType.NO_STRONG_VOTES_AFTER_POWER_CHANGE)
        if strong_count == 1:
            report.add_policy_issue(issue=IssueType.ONLY_ONE_STRONG_VOTE, warning=True)
        return report
