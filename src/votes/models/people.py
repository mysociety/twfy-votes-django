import datetime
from typing import Optional

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


class Person(DjangoVoteModel):
    id: PrimaryKey = None
    name: str
    memberships: DummyOneToMany["Membership"] = related_name("person")

    @classmethod
    def current(cls):
        """
        Those with a membership that is current.
        """
        return cls.objects.filter(memberships__end_date__gte=datetime.date.today())


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
    chamber_id: Dummy[Optional[int]] = None
    chamber: DoNothingForeignKey[Organization] = field(
        default=None, null=True, related_name="org_memberships"
    )
    post_label: str
    area_name: str
