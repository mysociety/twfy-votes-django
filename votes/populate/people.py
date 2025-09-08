import datetime
from itertools import groupby
from pathlib import Path
from typing import overload

import pandas as pd
import rich
from mysoc_validator import Popolo
from mysoc_validator.models.dates import ApproxDate, FixedDate
from mysoc_validator.models.popolo import Membership as PopoloMembership
from mysoc_validator.models.popolo import Person as PopoloPerson

from ..consts import ChamberSlug, OrganisationType
from ..models import Chamber, Membership, Organization, OrgMembershipCount, Person
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


def adjust_very_overlapping_time_ranges(popolo: Popolo, quiet: bool = False) -> Popolo:
    """
    These I think are outright errors but need more investigation.
    About 4 lots and a 300 historic MPs (who cares) whose previous membership overruns by days
    This later on causes issues with the membership counts, and duplicate divisions.
    """
    count = 0
    for person in popolo.persons:
        if not isinstance(person, PopoloPerson):
            continue
        grouped_membership = [
            (post_org_or_self_org(m), m)
            for m in person.memberships()
            if isinstance(m, PopoloMembership)
        ]
        grouped_membership.sort(key=lambda x: x[0])

        for org, memberships in groupby(grouped_membership, key=lambda x: x[0]):
            memberships = list(memberships)
            memberships.sort(key=lambda x: x[1].start_date)

            for index, (org, m) in enumerate(memberships):
                if index == 0:
                    continue
                previous = memberships[index - 1][1]

                if previous.end_date >= m.start_date:
                    proposed_end_date = resolve_date(
                        m.start_date, default=FixedDate.PAST
                    ) - datetime.timedelta(days=1)
                    if proposed_end_date < previous.start_date:
                        continue
                    previous.end_date = proposed_end_date
                    count += 1

    if not quiet:
        rich.print(f"Adjusted [blue]{count}[/blue] very overlapping time ranges")

    return popolo


def adjust_overlapping_time_ranges(popolo: Popolo, quiet: bool = False) -> Popolo:
    """
    Calculating down the line depend on consecutive time ranges rather than an overlap on the end date
    Ideally addressed at source.
    """
    count = 0
    for person in popolo.persons:
        person = person.self_or_redirect()
        memberships = person.memberships()
        memberships.sort(key=lambda m: m.start_date)
        for i, membership in enumerate(memberships[:-1]):
            next_membership = memberships[i + 1]
            if membership.end_date == next_membership.start_date:
                if membership.organization_id != next_membership.organization_id:
                    continue
                membership.end_date = membership.end_date - datetime.timedelta(days=1)  # type: ignore
                count += 1

    if not quiet:
        rich.print(f"Adjusted [blue]{count}[/blue] overlapping time ranges")

    return popolo


@import_register.register("people", ImportOrder.PEOPLE)
def import_popolo(quiet: bool = False):
    popolo_source = Path("data", "source", "people.json")

    popolo = Popolo.from_path(popolo_source)

    popolo = adjust_overlapping_time_ranges(popolo, quiet=quiet)
    popolo = adjust_very_overlapping_time_ranges(popolo, quiet=quiet)

    to_create = []
    for person in popolo.persons:
        if isinstance(person, PopoloPerson):
            all_names = person.names
            all_names.sort(key=lambda x: x.start_date, reverse=True)
            # limit down to note = "Main"
            all_names = [n for n in all_names if n.note == "Main"]
            latest_name = all_names[0].nice_name()

            item = Person(id=int_id(person.id), name=latest_name)

            to_create.append(item)

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
            classification=(
                OrganisationType(org.classification)
                if org.classification
                else OrganisationType.UNKNOWN
            ),
        )

        to_create.append(item)

    # Need to add an 'Unknown' party for unknown members
    to_create.append(
        Organization(
            slug="unknown",
            name="Unknown",
            classification=OrganisationType.PARTY,
        )
    )

    to_create = Organization.get_lookup_manager("slug").add_ids(to_create)

    Organization.objects.all().delete()
    Organization.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] organizations")

    org_slug_lookup = Organization.id_from_slug("slug")
    chamber_slug_lookup = Chamber.id_from_slug("slug")

    to_create = []

    for membership in popolo.memberships:
        if isinstance(membership, PopoloMembership):
            chamber_slug = ChamberSlug.from_parlparse(
                post_org_or_self_org(membership), passthrough=True
            )
            if chamber_slug in ["crown", "london-assembly"]:
                chamber_id = 0
            else:
                chamber_id = chamber_slug_lookup[chamber_slug]
            post = membership.post()
            post_label = post.role if post else ""
            area_name = post.area.name if post else ""
            effective_party = get_effective_party(membership.on_behalf_of_id)
            item = Membership(
                id=int_id(membership.id),
                person_id=int_id(membership.person_id),
                start_date=resolve_date(membership.start_date, FixedDate.PAST),
                end_date=resolve_date(membership.end_date, FixedDate.FUTURE),
                party_slug=membership.on_behalf_of_id or "",
                effective_party_slug=effective_party,
                party_id=org_slug_lookup.get(membership.on_behalf_of_id or ""),
                effective_party_id=org_slug_lookup.get(effective_party),
                chamber_id=chamber_id,
                chamber_slug=chamber_slug,
                area_name=area_name,
                post_label=post_label,
            )
            if chamber_id != 0:
                to_create.append(item)

    Membership.objects.all().delete()
    Membership.objects.bulk_create(to_create, batch_size=50000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] memberships")

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

    OrgMembershipCount.objects.all().delete()
    OrgMembershipCount.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] membership counts")
