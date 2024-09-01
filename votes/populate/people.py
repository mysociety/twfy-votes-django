import datetime
from pathlib import Path
from typing import overload

import rich
from mysoc_validator import Popolo
from mysoc_validator.models.dates import ApproxDate, FixedDate
from mysoc_validator.models.popolo import Membership as PopoloMembership
from mysoc_validator.models.popolo import Person as PopoloPerson

from ..consts import OrganisationType
from ..models.people import Membership, Organization, Person
from .register import ImportOrder, import_register


@overload
def int_id(value: str) -> int: ...


@overload
def int_id(value: None) -> None: ...


def int_id(value: str | None) -> int | None:
    if value is None:
        return
    return int(value.split("/")[-1])


def resolve_date(
    date: datetime.date | ApproxDate | None, default: datetime.date
) -> datetime.date:
    match date:
        case None:
            return FixedDate.FUTURE
        case datetime.date():
            return date
        case ApproxDate():
            return date.latest_date
        case _:
            raise ValueError(f"Unexpected date {date}")


@import_register.register("people", ImportOrder.PEOPLE)
def import_popolo(quiet: bool = False):
    popolo_source = Path("data", "source", "people.json")

    popolo = Popolo.from_path(popolo_source)

    to_create = []
    for person in popolo.persons:
        if isinstance(person, PopoloPerson):
            all_names = person.names
            all_names.sort(key=lambda x: x.start_date, reverse=True)
            latest_name = all_names[0].nice_name()

            item = Person(id=int_id(person.id), name=latest_name)

            to_create.append(item)

    with Person.disable_constraints():
        Person.objects.all().delete()
        Person.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] people")

    to_create = []

    for org in popolo.organizations:
        item = Organization(
            slug=org.id,
            name=org.name,
            classification=OrganisationType(org.classification)
            if org.classification
            else OrganisationType.UNKNOWN,
        )

        to_create.append(item)

    to_create = Organization.get_lookup_manager("slug").add_ids(to_create)

    with Organization.disable_constraints():
        Organization.objects.all().delete()
        Organization.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] organizations")

    org_slug_lookup = Organization.id_from_slug("slug")

    to_create = []

    for membership in popolo.memberships:
        if isinstance(membership, PopoloMembership):
            post = membership.post()
            post_label = post.role if post else ""
            area_name = post.area.name if post else ""
            item = Membership(
                id=int_id(membership.id),
                person_id=int_id(membership.person_id),
                start_date=resolve_date(membership.start_date, FixedDate.PAST),
                end_date=resolve_date(membership.end_date, FixedDate.FUTURE),
                party_slug=membership.on_behalf_of_id or "",
                on_behalf_of_id=org_slug_lookup.get(membership.on_behalf_of_id or ""),
                organization_id=org_slug_lookup.get(membership.organization_id or ""),
                area_name=area_name,
                post_label=post_label,
            )

            to_create.append(item)

    with Membership.disable_constraints():
        Membership.objects.all().delete()
        Membership.objects.bulk_create(to_create, batch_size=50000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] memberships")
