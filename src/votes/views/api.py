import datetime
from typing import Literal

from django.http import HttpRequest

from ninja import ModelSchema, NinjaAPI

from ..models.decisions import (
    Agreement,
    Division,
    DivisionBreakdown,
    DivisionPartyBreakdown,
    DivisionsIsGovBreakdown,
    Policy,
    PolicyAgreementLink,
    PolicyDivisionLink,
    PolicyGroup,
    Vote,
)
from ..models.people import Person

api = NinjaAPI(docs_url="/api", title="TheyWorkForYou Votes API")


class PersonSchema(ModelSchema):
    class Meta:
        model = Person
        fields = "__all__"


class DivisionBreakdownSchema(ModelSchema):
    class Meta:
        model = DivisionBreakdown
        fields = "__all__"


class DivisionPartyBreakdownSchema(ModelSchema):
    class Meta:
        model = DivisionPartyBreakdown
        fields = "__all__"


class DivisionsIsGovBreakdownSchema(ModelSchema):
    class Meta:
        model = DivisionsIsGovBreakdown
        fields = "__all__"


class VoteSchema(ModelSchema):
    class Meta:
        model = Vote
        exclude = ["id"]
        fields = "__all__"


class PersonWithVoteSchema(ModelSchema):
    votes: list[VoteSchema]

    class Meta:
        model = Person
        fields = "__all__"


class DivisionSchema(ModelSchema):
    class Meta:
        model = Division
        fields = "__all__"


class DivisionWithInfoSchema(ModelSchema):
    votes: list[VoteSchema]
    breakdowns: list[DivisionBreakdownSchema]
    party_breakdowns: list[DivisionPartyBreakdownSchema]
    is_gov_breakdowns: list[DivisionsIsGovBreakdownSchema]

    class Meta:
        model = Division
        fields = "__all__"


class AgreementSchema(ModelSchema):
    class Meta:
        model = Agreement
        fields = "__all__"


class PolicyGroupSchema(ModelSchema):
    class Meta:
        model = PolicyGroup
        exclude = ["id"]
        fields = "__all__"


class PolicyAgreementLinkSchema(ModelSchema):
    decision: AgreementSchema

    class Meta:
        model = PolicyAgreementLink
        exclude = ["id", "policy", "notes"]
        fields = "__all__"


class PolicyDivisionLinkSchema(ModelSchema):
    decision: DivisionSchema

    class Meta:
        model = PolicyDivisionLink
        exclude = ["id", "policy", "notes"]
        fields = "__all__"


class PolicySchema(ModelSchema):
    groups: list[PolicyGroupSchema]
    division_links: list[PolicyDivisionLinkSchema]
    agreement_links: list[PolicyAgreementLinkSchema]

    class Meta:
        model = Policy
        fields = "__all__"


@api.get(
    "/decisions/division/{chamber_slug}/{date}/{division_number}.json",
    response=DivisionWithInfoSchema,
)
def get_division(
    request: HttpRequest, chamber_slug: str, date: datetime.date, division_number: int
):
    return Division.objects.get(
        chamber_slug=chamber_slug, date=date, division_number=division_number
    )


@api.get("/people/{people_option}.json", response=list[PersonSchema])
def get_people(request: HttpRequest, people_option: Literal["current", "all"]):
    if people_option == "current":
        return Person.current()
    else:
        return Person.objects.all()


@api.get("/person/{person_id}.json", response=PersonSchema)
def get_person(request: HttpRequest, person_id: int):
    return Person.objects.get(id=person_id)


@api.get("/person/{person_id}/votes.json", response=PersonWithVoteSchema)
def get_person_with_votes(request: HttpRequest, person_id: int):
    return Person.objects.get(id=person_id)


@api.get(
    "/decisions/agreement/{chamber_slug}/{date}/{decision_ref}.json",
    response=AgreementSchema,
)
def get_agreement(
    request: HttpRequest, chamber_slug: str, date: datetime.date, decision_ref: str
):
    return Agreement.objects.get(
        chamber_slug=chamber_slug, date=date, decision_ref=decision_ref
    )


@api.get("/decisions/{chamber_slug}/{year}.json", response=list[DivisionSchema])
def get_divisions_by_year(request: HttpRequest, chamber_slug: str, year: int):
    return Division.objects.filter(chamber_slug=chamber_slug, date__year=year)


@api.get("/decisions/{chamber_slug}/{year}/{month}.json", response=list[DivisionSchema])
def get_divisions_by_month(
    request: HttpRequest, chamber_slug: str, year: int, month: int
):
    return Division.objects.filter(
        chamber_slug=chamber_slug, date__year=year, date__month=month
    )


@api.get("/policies.json", response=list[PolicySchema])
def get_policies(request: HttpRequest):
    return Policy.objects.all().prefetch_related("groups")


@api.get("/policy/{chamber_slug}/{status}/{group_slug}.json", response=PolicySchema)
def get_policy(request: HttpRequest, chamber_slug: str, status: str, group_slug: str):
    return Policy.objects.get(
        chamber_slug=chamber_slug, status=status, group_slug=group_slug
    )


@api.get("/policy/{policy_id}.json", response=PolicySchema)
def get_policy_by_id(request: HttpRequest, policy_id: int):
    return Policy.objects.get(id=policy_id)


# /policies/report
# /person/{person_id}/records/{chamber_slug}/{party_id}
# /twfy-compatible/popolo/{policy_id}.json
