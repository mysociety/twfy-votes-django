"""
To run analysis on the same day votes, we need to pull the information from the commons votes api.
These divisions will be ignored once an equivalent division is found in the mysociety data.

This is missing motion information, but allows party and distance calculations - and gives something to attach
whipping information to.

"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
import rich
from mysoc_validator import Popolo
from mysoc_validator.models.popolo import Chamber, IdentifierScheme
from pydantic import BaseModel, Field, RootModel

from votes.consts import StrVotePosition

from .register import ImportOrder, import_register


class MiniVote(BaseModel):
    division_id: str
    membership_id: int
    person_id: int
    vote: StrVotePosition


class MiniDivision(BaseModel):
    division_id: str
    chamber: str
    source_gid: str
    debate_gid: str
    division_title: str
    division_date: datetime.date
    division_number: int


class Member(BaseModel):
    MemberId: int
    Name: str
    Party: str
    SubParty: Optional[str]
    PartyColour: str
    PartyAbbreviation: Optional[str]
    MemberFrom: str
    ListAs: Optional[str]
    ProxyName: Optional[str]


class Division(BaseModel):
    DivisionId: int
    Date: datetime.datetime
    PublicationUpdated: str
    Number: int
    IsDeferred: bool
    EVELType: str
    EVELCountry: str
    Title: str
    AyeCount: int
    NoCount: int
    DoubleMajorityAyeCount: None
    DoubleMajorityNoCount: None
    AyeTellers: Optional[list[Member]] = Field(default_factory=list)
    NoTellers: Optional[list[Member]] = Field(default_factory=list)
    Ayes: list[Member] = Field(default_factory=list)
    Noes: list[Member] = Field(default_factory=list)
    FriendlyDescription: Optional[str] = None
    FriendlyTitle: Optional[str] = None
    NoVoteRecorded: list[Member] = Field(default_factory=list)
    RemoteVotingStart: None
    RemoteVotingEnd: None

    @property
    def pw_division_id(self):
        iso_date = self.Date.date().isoformat()
        return f"pw-{iso_date}-{self.Number}-commons"

    def to_mini_votes(self, popolo: Popolo) -> list[MiniVote]:
        def get_popolo_ids(mnis_id: int) -> tuple[int, int]:
            person = popolo.persons.from_identifier(
                str(mnis_id), scheme=IdentifierScheme.MNIS
            )
            membership = person.membership_on_date(
                self.Date.date(), chamber=Chamber.COMMONS
            )
            if not membership:
                raise ValueError(f"Person {person.id} not in chamber on {self.Date}")

            person_id = int(person.id.split("/")[-1])
            membership_id = int(membership.id.split("/")[-1])
            return person_id, membership_id

        def to_popolo_ids(ids: list[int]) -> list[tuple[int, int]]:
            return [get_popolo_ids(x) for x in ids]

        yes_ids = [person.MemberId for person in self.Ayes]
        no_ids = [person.MemberId for person in self.Noes]
        absent_ids = [person.MemberId for person in self.NoVoteRecorded]
        both_ids = [x for x in yes_ids if x in no_ids]
        if both_ids:
            yes_ids = [x for x in yes_ids if x not in both_ids]
            no_ids = [x for x in no_ids if x not in both_ids]
        yes_teller_ids = []
        no_teller_ids = []
        if self.AyeTellers:
            yes_teller_ids = [person.MemberId for person in self.AyeTellers]
        if self.NoTellers:
            no_teller_ids = [person.MemberId for person in self.NoTellers]

        votes: list[MiniVote] = []

        mappings = [
            (yes_ids, StrVotePosition.AYE),
            (no_ids, StrVotePosition.NO),
            (absent_ids, StrVotePosition.ABSENT),
            (yes_teller_ids, StrVotePosition.TELLAYE),
            (no_teller_ids, StrVotePosition.TELLNO),
            (both_ids, StrVotePosition.ABSTAIN),
        ]

        for ids, position in mappings:
            for person_id, membership_id in to_popolo_ids(ids):
                votes.append(
                    MiniVote(
                        division_id=self.pw_division_id,
                        membership_id=membership_id,
                        person_id=person_id,
                        vote=position,
                    )
                )

        return votes

    def to_mini_division(self) -> MiniDivision:
        return MiniDivision(
            division_id=self.pw_division_id,
            chamber="commons",
            source_gid="",
            debate_gid="",
            division_title=self.Title,
            division_date=self.Date.date(),
            division_number=self.Number,
        )

    @classmethod
    def from_api(cls, division_id: int) -> Division:
        url = f"https://commonsvotes-api.parliament.uk/data/division/{division_id}.json"
        response = httpx.get(url)
        response.raise_for_status()
        return cls.model_validate(response.json())


class DivisionSearchList(RootModel):
    root: list[Division]

    @classmethod
    def expand_from_partial(cls, partial: DivisionSearchList) -> DivisionSearchList:
        expanded_items = [Division.from_api(item.DivisionId) for item in partial.root]
        return cls(root=expanded_items)

    def __iter__(self):
        return iter(self.root)

    @classmethod
    def from_date(
        cls, *, start_date: datetime.date, end_date: datetime.date
    ) -> DivisionSearchList:
        params = {
            "queryParameters.startDate": start_date.isoformat(),
            "queryParameters.endDate": end_date.isoformat(),
        }

        url = "https://commonsvotes-api.parliament.uk/data/divisions.json/search"
        response = httpx.get(url, params=params)
        response.raise_for_status()
        partial = cls.model_validate(response.json())
        return cls.expand_from_partial(partial)

    def to_parquet(self, quiet: bool = False) -> None:
        popolo = Popolo.from_path(Path("data", "source", "people.json"))

        divisions = [item.to_mini_division() for item in self.root]

        votes: list[MiniVote] = []
        for division in self.root:
            votes.extend(division.to_mini_votes(popolo))

        div_path = Path("data", "compiled", "api_divisions.parquet")
        votes_path = Path("data", "compiled", "api_votes.parquet")

        if divisions:
            if not quiet:
                rich.print(f"Grabbing {len(divisions)} divisions from the Commons API")
            pd.DataFrame([x.model_dump() for x in divisions]).to_parquet(div_path)
        else:
            pd.DataFrame(columns=list(MiniDivision.model_fields.keys())).to_parquet(
                div_path
            )

        if votes:
            pd.DataFrame([x.model_dump() for x in votes]).to_parquet(votes_path)
            if not quiet:
                rich.print(f"Grabbing {len(votes)} votes from the Commons API")
        else:
            pd.DataFrame(columns=list(MiniVote.model_fields.keys())).to_parquet(
                votes_path
            )


@import_register.register("commons_votes_api", group=ImportOrder.API_VOTES)
def build_parquet_for_today(
    quiet: bool = False, update_since: datetime.date | None = None
):
    today = datetime.date.today()
    start_date = update_since or (today - datetime.timedelta(days=3))

    divisions = DivisionSearchList.from_date(start_date=start_date, end_date=today)
    divisions.to_parquet(quiet=quiet)
