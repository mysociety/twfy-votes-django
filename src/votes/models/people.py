from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from django.urls import reverse

import numpy as np
import pandas as pd

from twfy_votes.helpers.typed_django.models import (
    DoNothingForeignKey,
    Dummy,
    DummyOneToMany,
    PrimaryKey,
    field,
    related_name,
)

from ..consts import ChamberSlug, OrganisationType
from .base_model import DjangoVoteModel

if TYPE_CHECKING:
    from .decisions import Chamber, PolicyComparisonPeriod, Vote, VoteDistribution


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

    def votes_url(self):
        return reverse("person_votes", kwargs={"person_id": self.id})

    def policy_distribution_groups(self):
        print("here")
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
            print(group)
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

    def votes_df(self) -> pd.DataFrame:
        from .decisions import UrlColumn

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
            for v in self.votes.all()
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
