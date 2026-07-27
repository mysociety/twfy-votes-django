"""
Tag decisions with legislation when possible
"""

from __future__ import annotations

import datetime
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

    # Build word sets from former titles for fallback matching when
    # Parliament renames a bill (e.g. drops [HL] suffix on chamber change)
    if "former_title" in bills_df.columns:
        bills_df["former_title"] = (
            bills_df["former_title"]
            .fillna("")
            .apply(lambda x: fix_bills_title(x) if x else "")
        )
        bills_df["former_title_set"] = bills_df["former_title"].apply(
            lambda x: set(slugify(x).split(" ")) if isinstance(x, str) and x else set()
        )
    else:
        bills_df["former_title_set"] = [set()] * len(bills_df)

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


def check_set_overlap(our_set: set[str], their_set: set[str]) -> bool:
    """
    Check if our_set is a subset of their_set,
    ignoring the [hl] chamber marker which is inconsistently present.
    """
    clean_our = our_set - {"[hl]"}
    clean_their = their_set - {"[hl]"}
    return len(clean_our) > 0 and clean_our.issubset(clean_their)


def get_division_df(
    verbose: bool = False,
    update_since: datetime.date | None = None,
) -> pd.DataFrame:
    """
    Map decisions to possible tags and legislation
    """

    bills_df = get_bills_df()
    starting_date = update_since.isoformat() if update_since else "2024-01-01"

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
            bills_df["title_set"].apply(lambda x: check_set_overlap(legislation_set, x))
        ]

        # Fallback: if no match on current title, try the bill's former title
        # (covers cases where Parliament has renamed the bill since the vote)
        if len(match_df) == 0:
            match_df = bills_df[
                bills_df["former_title_set"].apply(
                    lambda x: check_set_overlap(legislation_set, x)
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
                # No exact title match and multiple options
                # pick the bill most recently active
                # near the decision date (e.g. "Finance Bill" across sessions)
                match_df = match_df.copy()
                match_df["time_distance"] = match_df["last_update"].apply(
                    lambda x: abs(pd.Timestamp(d.date) - pd.Timestamp(x))
                )
                match_df = match_df.sort_values("time_distance").head(1)
                if verbose:
                    rich.print(
                        f"Multiple matches for {ldn}, "
                        f"selected closest: {match_df.iloc[0]['title']}"
                    )

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
def vote_analysis(quiet: bool = False, update_since: datetime.date | None = None):
    """
    Map decisions to possible tags and legislation
    """

    # get the division df
    df = get_division_df(verbose=False, update_since=update_since)

    tags_df = df[["legislation", "url", "leg_chamber", "leg_id"]]
    tags_df["slug"] = tags_df["legislation"].apply(full_slugify)
    tags_df = tags_df.drop_duplicates("slug")

    # Maps (tag_type, slug) -> id for all existing tags
    lookup = DecisionTag.id_from_slugs("tag_type", "slug")

    # Maps leg_id -> existing tag, so we can detect bill renames
    # (same leg_id but different slug) and update in-place
    leg_id_to_existing_tag: dict[str, DecisionTag] = {}
    for tag in DecisionTag.objects.filter(tag_type=TagType.LEGISLATION):
        extra_data = tag.extra_data or {}
        if not isinstance(extra_data, dict):
            continue
        stored_leg_id = extra_data.get("leg_id", "")
        if stored_leg_id:
            leg_id_to_existing_tag[stored_leg_id] = tag

    tags: list[DecisionTag] = []

    def markdown_url(url: str) -> str:
        if url.startswith("http"):
            return f"[Link to Parliamentary Tracker]({url})"
        return url

    existing_slugs: list[str] = []
    for i, row in tags_df.iterrows():
        slug = row["slug"]
        leg_id = str(row["leg_id"])
        existing_id = lookup.get((TagType.LEGISLATION, slug))

        # Slug not found but same leg_id exists — bill was renamed,
        # reuse the existing tag and slug so the slug updates in-place
        if existing_id is None and leg_id in leg_id_to_existing_tag:
            existing_id = leg_id_to_existing_tag[leg_id].id
            slug = leg_id_to_existing_tag[leg_id].slug

        existing_slugs.append(slug)
        tags.append(
            DecisionTag(
                id=existing_id,
                slug=slug,
                name=row["legislation"],
                desc=markdown_url(row["url"]),
                extra_data={
                    "chamber": str(row["leg_chamber"]),
                    "leg_id": leg_id,
                },
                tag_type=TagType.LEGISLATION,
            )
        )

    to_create = [x for x in tags if x.id is None]
    to_update = [x for x in tags if x.id is not None]

    to_remove = DecisionTag.objects.filter(
        tag_type=TagType.LEGISLATION,
        slug__in=[x for x in existing_slugs if x not in tags_df["slug"].tolist()],
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
