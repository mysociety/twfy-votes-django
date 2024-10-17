from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from django.urls import reverse

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
    from .decisions import Chamber


class Person(DjangoVoteModel):
    id: PrimaryKey = None
    name: str
    memberships: DummyOneToMany["Membership"] = related_name("person")

    def votes_url(self):
        return reverse("person_votes", kwargs={"person_id": self.id})

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
