import datetime
from typing import Annotated, Optional

from django.db import models

from pydantic.fields import Field as PydanticField

from .consts import Chamber, ChamberSlug
from .helpers.typed_model import TypedModel

PrimaryKey = Annotated[Optional[int], models.AutoField(primary_key=True)]
CharField = Annotated[
    str, models.CharField(max_length=255), PydanticField(max_length=255)
]

TextField = Annotated[str, models.TextField()]
Len10CharField = Annotated[
    str, models.CharField(max_length=10), PydanticField(max_length=255)
]
Len2CharField = Annotated[
    str, models.CharField(max_length=2), PydanticField(max_length=255)
]
IntegerField = Annotated[int, models.IntegerField()]
PositiveIntegerField = Annotated[
    int, models.PositiveIntegerField(), PydanticField(gt=0)
]
DateField = Annotated[datetime.date, models.DateField()]
DateTimeField = Annotated[datetime.datetime, models.DateTimeField()]
OptionalDateTimeField = Annotated[
    Optional[datetime.datetime], models.DateTimeField(null=True)
]


class GovernmentParty(TypedModel):
    id: PrimaryKey = None
    label: CharField
    chamber: ChamberSlug
    party: CharField
    start_date: DateField
    end_date: DateField


class Division(TypedModel):
    id: PrimaryKey = None
    key: CharField
    chamber_slug: ChamberSlug
    date: DateField
    division_id: IntegerField
    division_number: IntegerField
    division_name: CharField
    source_url: CharField
    motion: CharField
    manual_motion: CharField
    debate_url: CharField
    source_gid: CharField
    debate_gid: CharField
    clock_time: CharField = ""
    voting_cluster: CharField = ""

    @property
    def chamber(self) -> Chamber:
        return Chamber(slug=self.chamber_slug)


class Agreement(TypedModel):
    id: PrimaryKey
    chamber_slug: ChamberSlug
    date: DateField
    decision_ref: CharField
    decision_name: IntegerField
    voting_cluster: CharField = "Agreement"
