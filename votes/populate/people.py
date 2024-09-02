import datetime
from pathlib import Path
from typing import overload

import pandas as pd
import rich
from mysoc_validator import Popolo
from mysoc_validator.models.dates import ApproxDate, FixedDate
from mysoc_validator.models.popolo import Membership as PopoloMembership
from mysoc_validator.models.popolo import Person as PopoloPerson

from ..consts import ChamberSlug, OrganisationType
from ..models.people import Membership, Organization, OrgMembershipCount, Person
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


def get_effective_party(party_slug: str | None) -> str:
    if party_slug == "labourco-operative":
        return "labour"
    return party_slug or ""


def minus_one_date(date: datetime.date) -> datetime.date:
    """
    Give one day before an ISO date
    """
    # special case for 9999 - don't need to do day before
    if date == "9999-12-31":
        return date
    return date - pd.Timedelta(days=1)


def post_org_or_self_org(m: PopoloMembership):
    post = m.post()
    if post is None:
        org = m.organization_id
    else:
        org = post.organization_id

    if org is None:
        raise ValueError(f"No organization for membership {m}")
    return org


def membership_on_date(popolo: Popolo) -> pd.DataFrame:
    """
    From the popolo file create a dataframe of memberships on any given date
    """

    data = [
        {
            "chamber": ChamberSlug.from_parlparse(
                post_org_or_self_org(m), passthrough=True
            ),
            "start_date": resolve_date(m.start_date, FixedDate.PAST),
            "end_date": resolve_date(m.end_date, FixedDate.FUTURE),
        }
        for m in popolo.memberships
        if isinstance(m, PopoloMembership)
    ]

    df = pd.DataFrame(data)

    # We want to create a new dataframe with value, date, chamber
    # we are converting the start and end dates into a list of events
    # if there is a start date, there is a value of 1
    # if there is an end date, there is a value of -1

    # we are going to use the melt function to do this
    ndf = pd.melt(
        df,
        id_vars=["chamber"],
        value_vars=["start_date", "end_date"],
        var_name="str_event",
        value_name="date",
    ).sort_values(["chamber", "date"])

    ndf["event"] = ndf["str_event"].apply(lambda x: 1 if x == "start_date" else -1)

    def get_range_counts(df: pd.DataFrame) -> pd.DataFrame:
        # remove none values - our end events that aren't interesting
        df = df[df["date"].notna()].copy(deep=True)
        # use cum sum to get the number of members at any given time
        # obvs this is wrong in the early days
        df["members_count"] = df["event"].cumsum()
        # reduce to unique dates - get the last members count for each date
        df = df.drop_duplicates("date", keep="last")
        # reexpress this as ranges e.g. start_date, end_date, members_count
        df["end_date"] = (
            df["date"].shift(-1, fill_value=FixedDate.FUTURE).apply(minus_one_date)
        )
        df = df[["date", "end_date", "members_count"]]
        df = df.rename(columns={"date": "start_date"})
        return df

    dfs = []

    for chamber, chamber_df in ndf.groupby("chamber"):
        if chamber in list(ChamberSlug):
            range_df = get_range_counts(chamber_df)
            range_df["chamber"] = chamber
            dfs.append(range_df)

    final = pd.concat(dfs)

    return final


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

    # make sure our internal slug matches our enum rather than the longer form in the popolo file
    for org in popolo.organizations:
        item = Organization(
            slug=ChamberSlug.from_parlparse(org.id, passthrough=True),
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
                effective_party_slug=get_effective_party(membership.on_behalf_of_id),
                party_id=org_slug_lookup.get(membership.on_behalf_of_id or ""),
                chamber_id=org_slug_lookup.get(
                    ChamberSlug.from_parlparse(
                        post_org_or_self_org(membership), passthrough=True
                    )
                ),
                area_name=area_name,
                post_label=post_label,
            )

            to_create.append(item)

    with Membership.disable_constraints():
        Membership.objects.all().delete()
        Membership.objects.bulk_create(to_create, batch_size=50000)

    count_data = membership_on_date(popolo)

    to_create = []

    for _, row in count_data.iterrows():
        item = OrgMembershipCount(
            chamber_slug=row["chamber"],
            chamber_id=org_slug_lookup[row["chamber"]],
            start_date=row["start_date"],
            end_date=row["end_date"],
            count=row["members_count"],
        )

        to_create.append(item)

    with OrgMembershipCount.disable_constraints():
        OrgMembershipCount.objects.all().delete()
        OrgMembershipCount.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] membership counts")
