import datetime
from typing import Optional

from ..consts import OrganisationType
from .base_model import DjangoVoteModel
from .typed_django.models import (
    DoNothingForeignKey,
    Dummy,
    DummyOneToMany,
    PrimaryKey,
    field,
    related_name,
)


class Person(DjangoVoteModel):
    id: PrimaryKey = None
    name: str
    memberships: DummyOneToMany["Membership"] = related_name("person")


class Organization(DjangoVoteModel):
    id: PrimaryKey = None
    slug: str
    name: str
    classification: OrganisationType = OrganisationType.UNKNOWN
    org_memberships: DummyOneToMany["Membership"] = related_name("organization")
    party_memberships: DummyOneToMany["Membership"] = related_name("on_behalf_of")


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
    on_behalf_of_id: Dummy[Optional[int]] = None
    on_behalf_of: DoNothingForeignKey[Organization] = field(
        default=None, null=True, related_name="party_memberships"
    )
    organization_id: Dummy[Optional[int]] = None
    organization: DoNothingForeignKey[Organization] = field(
        default=None, null=True, related_name="org_memberships"
    )
    post_label: str
    area_name: str
