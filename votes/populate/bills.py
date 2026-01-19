"""
Download bill datasets from Parliamentary datasets to be used later.
"""

import datetime
from functools import lru_cache
from pathlib import Path
from typing import Self

from django.conf import settings

import httpx
import pandas as pd
import rich
from pydantic import BaseModel, Field, RootModel, TypeAdapter

from .register import ImportOrder, import_register


class Stage(BaseModel):
    id: int
    stageId: int
    sessionId: int
    description: str
    abbreviation: str
    house: str
    stageSittings: list
    sortOrder: int


class Bill(BaseModel):
    billId: int
    shortTitle: str
    formerShortTitle: str | None = None
    currentHouse: str | None = None
    originatingHouse: str | None = None
    lastUpdate: datetime.datetime
    billWithdrawn: None | datetime.datetime
    isDefeated: bool
    billTypeId: int
    introducedSessionId: int
    includedSessionIds: list
    isAct: bool
    currentStage: Stage | None = None

    @property
    def url(self):
        return f"https://bills.parliament.uk/bills/{self.billId}"

    @classmethod
    def fetch_data(cls) -> list[Self]:
        BillList = TypeAdapter(list[cls])

        url = "https://bills-api.parliament.uk/api/v1/Bills"
        skip = 0
        take = 100

        items = []

        max_results = 1
        while len(items) < max_results:
            params = {
                "Skip": skip,
                "Take": take,
            }
            request = httpx.get(url, params=params, timeout=30)

            data = request.json()
            max_results = data["totalResults"]
            items.extend(data["items"])
            skip += take

        return BillList.validate_python(items)


class ScotSession(BaseModel):
    ID: int
    ShortName: str
    Name: str
    StartDate: datetime.datetime
    EndDate: datetime.datetime | None = None

    @classmethod
    def fetch_data(cls) -> list[Self]:
        scot_url = "https://data.parliament.scot/api/sessions/json"
        scot_data = httpx.get(scot_url, timeout=30).json()
        adaptor = TypeAdapter(list[cls])
        scot_data = adaptor.validate_python(scot_data)
        return scot_data


class ScotSessionLookup(RootModel):
    root: list[ScotSession]

    @classmethod
    @lru_cache
    def fetch_data(cls) -> Self:
        return cls(ScotSession.fetch_data())

    def session_for_date(self, date: datetime.datetime) -> ScotSession | None:
        for session in self.root:
            if session.StartDate <= date and (
                session.EndDate is None or session.EndDate >= date
            ):
                return session
        return None


class ScotBillStage(BaseModel):
    ID: int
    BillID: int
    BillStageTypeID: int
    StageDate: datetime.datetime | None = None

    @classmethod
    def fetch_data(cls) -> list[Self]:
        scot_url = "https://data.parliament.scot/api/billstages/json"
        scot_data = httpx.get(scot_url, timeout=30).json()
        adaptor = TypeAdapter(list[cls])
        scot_data = adaptor.validate_python(scot_data)
        return scot_data


class ScotBill(BaseModel):
    ID: int
    Reference: str
    ShortName: str
    FullName: str
    Stages: list[ScotBillStage] = Field(default_factory=list)

    @property
    def slug(self):
        # this is fullname, removing punctuation other than space,
        # replacing space with -
        # and lowercasing

        # remove punctuation
        slug = "".join(c for c in self.FullName if c.isalnum() or c.isspace()).strip()
        slug = slug.replace(" ", "-")
        slug = slug.lower()
        return slug

    @property
    def first_date(self) -> datetime.datetime | None:
        dates = [x.StageDate for x in self.Stages if x.StageDate is not None]
        if len(dates) == 0:
            return None
        # get the first stage date
        return min(dates)

    @property
    def last_date(self) -> datetime.datetime | None:
        dates = [x.StageDate for x in self.Stages if x.StageDate is not None]
        if len(dates) == 0:
            return None
        # get the last stage date
        return max(dates)

    @property
    def url(self):
        slug = self.slug
        session_slug = self.session.ShortName
        return f"https://www.parliament.scot/bills-and-laws/bills/{session_slug}/{slug}"

    @property
    def session(self) -> ScotSession:
        session_lookup = ScotSessionLookup.fetch_data()
        if self.first_date is None:
            return session_lookup.root[-1]
        # get the session for the first stage date
        session = session_lookup.session_for_date(self.first_date)
        if session is None:
            raise ValueError(f"Session not found for {self.first_date}")
        return session

    @classmethod
    def fetch_data(cls) -> list[Self]:
        scot_url = "https://data.parliament.scot/api/bills/json"
        scot_data = httpx.get(scot_url, timeout=30).json()
        adaptor = TypeAdapter(list[cls])
        scot_data = adaptor.validate_python(scot_data)

        # fetch stages - which we need to get the first date
        # to get the url
        scot_stages = ScotBillStage.fetch_data()
        scot_lookup = {x.BillID: x for x in scot_stages}
        # add stages to bills
        for bill in scot_data:
            bill.Stages = []
            if bill.ID in scot_lookup:
                bill.Stages.append(scot_lookup[bill.ID])

        return scot_data


def get_bills() -> pd.DataFrame:
    """Fetches the bills from the API and returns a DataFrame."""

    bill_list = Bill.fetch_data()

    data = [
        {
            "chamber": "uk",
            "id": x.billId,
            "title": x.shortTitle,
            "url": x.url,
            "last_update": x.lastUpdate,
        }
        for x in bill_list
    ]

    return pd.DataFrame(data)


def get_scot_bills() -> pd.DataFrame:
    scot_data = ScotBill.fetch_data()

    scot_items = [
        {
            "chamber": "scotland",
            "id": x.ID,
            "title": x.FullName,
            "url": x.url,
            "last_update": x.last_date,
        }
        for x in scot_data
    ]

    return pd.DataFrame(scot_items)


@import_register.register("bills", group=ImportOrder.LOOKUPS)
def import_chambers(quiet: bool = False):
    """Imports the bills from the API and returns a DataFrame."""
    if not quiet:
        rich.print("[green]Importing bills[/green]")

    # get the bills
    if not quiet:
        rich.print("Fetching UK bills")
    df = get_bills()
    if not quiet:
        rich.print("Fetching Scottish bills")
    scot_df = get_scot_bills()

    # combine the dataframes
    df = pd.concat([df, scot_df], ignore_index=True)

    # sort by last update
    df.sort_values(by=["last_update"], ascending=False, inplace=True)

    source_dir = Path(settings.BASE_DIR) / "data" / "source"

    source_dir.mkdir(parents=True, exist_ok=True)

    df.to_parquet(source_dir / "bills.parquet", index=False)

    if not quiet:
        rich.print(f"Created a lookup with [green]{len(df)}[/green] bills")
