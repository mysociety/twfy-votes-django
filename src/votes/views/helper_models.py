from __future__ import annotations

import datetime
from dataclasses import dataclass
from itertools import groupby

import pandas as pd
from pydantic import BaseModel

from twfy_votes.helpers.routes import RouteApp

from ..consts import PolicyGroupSlug
from ..models.decisions import (
    Agreement,
    Chamber,
    Division,
    Policy,
    PolicyGroup,
    UrlColumn,
    VoteDistribution,
)

app = RouteApp(app_name="votes")


@dataclass
class DivisionSearch:
    start_date: datetime.date
    end_date: datetime.date
    chamber: Chamber
    decisions: list[Division | Agreement]

    def decisions_df(self) -> pd.DataFrame:
        data = [
            {
                "Date": d.date,
                "Division": UrlColumn(url=d.url(), text=d.safe_decision_name()),
                "Vote Type": d.vote_type(),
                "Powers": d.motion_uses_powers(),
                "Voting Cluster": d.voting_cluster()["desc"],
            }
            for d in self.decisions
        ]

        return pd.DataFrame(data=data)


@dataclass
class ChamberPolicyGroup:
    name: str
    policies: list[Policy]


@dataclass
class PolicyCollection:
    groups: list[PolicyDisplayGroup]

    def __iter__(self):
        return iter(self.groups)

    @classmethod
    def from_distributions(
        cls, distributions: list[VoteDistribution]
    ) -> list[PolicyDisplayGroup]:
        def get_key(v: VoteDistribution) -> str:
            return (
                f"{v.policy_id}-{v.person_id}-{v.period_id}-{v.chamber_id}-{v.party_id}"
            )

        sorted_list = sorted(distributions, key=get_key)

        pp_list: list[PairedPolicy] = []

        for _, group in groupby(sorted_list, key=get_key):
            group = list(group)
            our_key = [x for x in group if x.is_target]
            their_key = [x for x in group if not x.is_target]
            if len(our_key) > 1 or len(their_key) > 1:
                raise ValueError("Too many distributions for the same policy")
            if len(our_key) == 0:
                raise ValueError("No distribution for the target")
            our_key = our_key[0]
            if len(their_key) == 0:
                print("using other key")
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
            PolicyDisplayGroup(name="Significant Policies", paired_policies=sig_links)
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
                        paired_policies=grouped_items,
                    )
                )

        return groups


@dataclass
class PolicyDisplayGroup:
    name: str
    paired_policies: list[PairedPolicy]

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
            item = GroupTableItem(
                policy_name=str(
                    UrlColumn(
                        url=link.policy.url(),
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


@dataclass
class PairedPolicy:
    policy: Policy
    own_distribution: VoteDistribution
    other_distribution: VoteDistribution

    @property
    def comparison_score_difference(self) -> float:
        return (
            self.own_distribution.distance_score
            - self.other_distribution.distance_score
        )

    @property
    def significant_difference(self) -> bool:
        own_score = self.own_distribution.distance_score
        other_score = self.other_distribution.distance_score
        if own_score < 0.4 and other_score > 0.6:
            return True
        if own_score > 0.6 and other_score < 0.4:
            return True
        return False
