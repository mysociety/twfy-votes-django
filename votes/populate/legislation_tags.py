"""
Tag decisions with legislation when possible
"""

import html
import re

import pandas as pd
import rich

from votes.consts import ChamberSlug
from votes.models import Agreement, Division

from ..consts import TagType
from ..models import AgreementTagLink, DecisionTag, DivisionTagLink
from .register import ImportOrder, import_register


def full_slugify(s: str) -> str:
    """
    Remove all puntation, spaces to underscore, lowercase
    """
    slug = s.strip()
    slug = re.sub(r"[^\w\s]", "", slug).strip()
    slug = re.sub(r"\s+", "_", slug)
    slug = slug.lower()
    return slug


def slugify(s: str) -> str:
    slug = s
    slug = slug.lower().strip()
    return slug


def fix_bills_title(title: str) -> str:
    """
    Fix the title of a bill by replacing ' Act' with ' Bill'.
    """
    title = title.strip()
    if " Act" in title:
        # if a year straight after act, store
        title = title.replace(" Act", " Bill")
        # regular expression to find a year in a string and extract it
        match = re.search(r"\b\d{4}\b", title)
        if match:
            year = match.group(0)
            # replace the year with empty string
            title = title.replace(year, "")
            # remove any trailing spaces
            title = title.strip()
            # if there is a space at the end, remove it
            if title.endswith(" "):
                title = title[:-1]
            # add the year back in brackets
            title = f"{title} ({year})"
        return title

    return title


def get_bills_df() -> pd.DataFrame:
    """
    Create a df of bills - adjusting acts that have *happened* to be bills.
    """

    bills_df = pd.read_parquet("data/source/bills.parquet")

    bills_df["original_title"] = bills_df["title"]
    bills_df["title"] = bills_df["title"].apply(fix_bills_title)

    # drop duplicates on title
    bills_df["ltitle"] = bills_df["title"].str.lower().str.strip()

    # set NoT in last_update column to current date
    bills_df["last_update"] = bills_df["last_update"].replace(
        pd.NaT,  # type: ignore
        pd.Timestamp.now(),
    )

    bills_df = bills_df.drop_duplicates("ltitle")
    bills_df["title_set"] = bills_df["title"].apply(
        lambda x: set(slugify(x).split(" ")) if isinstance(x, str) else set()
    )
    return bills_df


def extract_legislation(s: str) -> str:
    """
    Extract legislation from decision name strings
    """
    s = html.unescape(s)

    to_remove = [
        "(Ways and Means)",
        "(Programme)",
        "(Carry-over)",
        "Reasons Committee",
        "Reasoned amendment on ",
    ]
    for r in to_remove:
        if r in s:
            s = s.replace(r, "")

    if s.startswith("Approve:"):
        return s[8:]

    if s.startswith("Leave for Bill:"):
        s = s.replace("Leave for Bill:", "")
        if "Bill" not in s:
            return s.strip() + " Bill"
        return s

    if "Bill Report Stage" in s:
        s = s.replace("Bill Committee Stage", "Bill")

    if "Bill Committee Stage" in s:
        s = s.replace("Bill Committee Stage", "Bill")

    if "Bill Committee" in s:
        s = s.replace("Bill Committee", "Bill")

    # get first position of ' bill' in s.lower
    pos = s.lower().find(" bill")
    # now we need to find what's the dividing character in this case
    # does one of ["-", ":"] appear within 5 characters of the position?

    divider = ""
    potential_dividers = [" - ", ":", " — "]
    for c in potential_dividers:
        if c in s[pos + 5 : pos + 15]:
            divider = c

    # if no divider after, work backwards from the position
    # until we hit a potential divider, or the start of the string
    if not divider:
        for c in potential_dividers:
            if c in s[:pos]:
                divider = c
                break

    if divider:
        parts = [x.strip() for x in s.split(divider)]
        # return the one that contains bill
        for part in parts:
            if "bill" in part.lower():
                return part.strip()

    if "Bill" in s:
        # cut off after Bill
        pos = s.lower().find(" bill") + 5
        if pos > 0:
            s = s[:pos]
        return s.strip()
    return ""


def check_set_overlap(our_set: set, their_set: set) -> bool:
    """
    Check if there is any overlap between two sets.
    """
    is_subset = our_set.issubset(their_set)
    remainder_set = their_set - our_set
    if "[hl]" in remainder_set:
        return False
    return is_subset


def get_division_df(verbose: bool = False) -> pd.DataFrame:
    """
    Map decisions to possible tags and legislation
    """

    bills_df = get_bills_df()
    starting_date = "2024-01-01"

    divisions = Division.objects.filter(
        date__gte=starting_date,
        chamber__slug__in=[
            ChamberSlug.COMMONS,
            ChamberSlug.LORDS,
            ChamberSlug.SCOTLAND,
        ],
    ).prefetch_related("motion")
    agreements = Agreement.objects.filter(date__gte=starting_date).prefetch_related(
        "motion"
    )

    decisions = list(divisions) + list(agreements)

    items = []

    for d in decisions:
        dn = d.safe_decision_name()
        ldn = extract_legislation(dn)

        if ldn == "Finance Bill":
            ldn = f"Finance Bill ({d.date.year})"
        if ldn == "Finance (No. 2) Bill":
            ldn = f"Finance Bill (No. 2) ({d.date.year})"

        if not ldn:
            continue
        url = ""
        leg_id = ""
        legislation_set = set(slugify(ldn).split(" "))

        # a match is when the above set if a complete subset of the title_set

        match_df = bills_df[
            bills_df["title_set"].apply(
                lambda x: check_set_overlap(legislation_set, x)
                and len(legislation_set) > 0
            )
        ]

        if len(match_df) > 1:
            # see if there's a direct match on the set

            direct_match = match_df[
                match_df["title"].str.lower().str.strip() == ldn.lower().strip()
            ]

            if len(direct_match) == 1:
                match_df = direct_match
            else:
                # restrict further on time
                if verbose:
                    print(f"Multiple matches for {ldn}:")
                    print(f"{d.date}")
                for i, row in match_df.iterrows():
                    distance = abs(
                        pd.Timestamp(d.date) - pd.Timestamp(row["last_update"])
                    )
                    if verbose:
                        print(f"{i}: {row['title']}: {distance.days} days")

        if len(match_df) == 1:
            # get the first match
            legislation = match_df.iloc[0]
            old_ldn = ldn.lower().strip()
            new_ldn = legislation["title"].lower().strip()
            if old_ldn != new_ldn:
                if verbose:
                    rich.print(f"Upgrading: {old_ldn} to {new_ldn}")
            ldn = legislation["title"].strip()
            url = legislation["url"]
            leg_id = legislation["id"]
            leg_chamber = legislation["chamber"]

        items.append(
            {
                "dtype": d.decision_type,
                "leg_id": leg_id,
                "leg_chamber": leg_chamber,
                "id": d.id,
                "name": dn,
                "legislation": ldn.strip(),
                "url": url,
            }
        )

    df = pd.DataFrame(items)

    return df


@import_register.register("legislation_tag", group=ImportOrder.DIVISION_ANALYSIS)
def vote_analysis(quiet: bool = False):
    """
    Map decisions to possible tags and legislation
    """

    # get the division df
    df = get_division_df(verbose=False)

    tags_df = df[["legislation", "url", "leg_chamber", "leg_id"]]
    tags_df["slug"] = tags_df["legislation"].apply(full_slugify)
    tags_df = tags_df.drop_duplicates("slug")

    lookup = DecisionTag.id_from_slugs("tag_type", "slug")
    all_exisiting_slugs = [x[1] for x in lookup.keys() if x[0] == TagType.LEGISLATION]

    tags: list[DecisionTag] = []

    def markdown_url(url: str) -> str:
        if url.startswith("http"):
            return f"[Link to Parliamentary Tracker]({url})"
        return url

    for i, row in tags_df.iterrows():
        if row["slug"] not in lookup:
            tags.append(
                DecisionTag(
                    id=lookup.get((TagType.LEGISLATION, row["slug"])),
                    slug=row["slug"],
                    name=row["legislation"],
                    desc=markdown_url(row["url"]),
                    extra_data={
                        "chamber": str(row["leg_chamber"]),
                        "leg_id": str(row["leg_id"]),
                    },
                    tag_type=TagType.LEGISLATION,
                )
            )

    to_create = [x for x in tags if x.id is None]
    to_update = [x for x in tags if x.id is not None]
    to_remove = DecisionTag.objects.filter(
        tag_type=TagType.LEGISLATION,
        slug__in=[x for x in all_exisiting_slugs if x not in tags_df["slug"].tolist()],
    )

    if not quiet:
        rich.print(f"[blue]Creating {len(to_create)} tags[/blue]")
        rich.print(f"[blue]Updating {len(to_update)} tags[/blue]")
        rich.print(f"[blue]Removing {len(to_remove)} tags[/blue]")

    if to_create:
        to_create = DecisionTag.objects.bulk_create(to_create, batch_size=1000)
    if to_update:
        DecisionTag.objects.bulk_update(
            to_update, ["name", "desc", "extra_data"], batch_size=1000
        )
    if to_remove:
        DecisionTag.objects.filter(
            id__in=to_remove.values_list("id", flat=True)
        ).delete()

    tags = to_create + to_update
    legislation_name_to_tag = {x.name: x for x in tags}

    division_links = []
    agreement_links = []

    for i, row in df.iterrows():
        if row["legislation"] in legislation_name_to_tag:
            tag = legislation_name_to_tag[row["legislation"]]
            if not tag.id:
                continue
            if row["dtype"] == "Division":
                division_links.append(
                    DivisionTagLink(
                        division_id=row["id"],
                        tag_id=tag.id,
                    )
                )
            else:
                agreement_links.append(
                    AgreementTagLink(
                        agreement_id=row["id"],
                        tag_id=tag.id,
                    )
                )
    DivisionTagLink.sync_tags(division_links, quiet=quiet, clear_absent=True)
    AgreementTagLink.sync_tags(agreement_links, quiet=quiet, clear_absent=True)
