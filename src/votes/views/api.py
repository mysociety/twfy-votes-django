import datetime
from typing import Literal

from django.http import HttpRequest

from ninja import ModelSchema, NinjaAPI
from pydantic import BaseModel

from ..consts import PolicyStatus
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
    VoteDistribution,
)
from ..models.people import Person
from .helper_models import PairedPolicy, PolicyDisplayGroup, PolicyReport
from .twfy_bridge import PopoloPolicy

api = NinjaAPI(docs_url="/api", title="TheyWorkForYou Votes API")


class VoteDistributionSchema(ModelSchema):
    class Meta:
        model = VoteDistribution
        fields = "__all__"


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
    person: PersonSchema

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
    overall_breakdowns: list[DivisionBreakdownSchema]
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


class PairedPolicySchema(BaseModel):
    policy: PolicySchema
    own_distribution: VoteDistributionSchema
    other_distribution: VoteDistributionSchema
    comparison_score_difference: float
    significant_difference: bool

    @classmethod
    def from_basic(cls, paired_policy: PairedPolicy):
        return cls.model_construct(
            policy=PolicySchema.from_orm(paired_policy.policy),
            own_distribution=VoteDistributionSchema.from_orm(
                paired_policy.own_distribution
            ),
            other_distribution=VoteDistributionSchema.from_orm(
                paired_policy.other_distribution
            ),
            comparison_score_difference=paired_policy.comparison_score_difference,
            significant_difference=paired_policy.significant_difference,
        )


class PolicyDisplayGroupSchema(BaseModel):
    name: str
    paired_policies: list[PairedPolicySchema]

    @classmethod
    def from_basic(cls, group: PolicyDisplayGroup):
        return cls(
            name=group.name,
            paired_policies=[
                PairedPolicySchema.from_basic(x) for x in group.paired_policies
            ],
        )


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
    "/person/{person_id}/policies/{chamber_slug}/{party_slug}/{period_slug}.json",
    response=list[PolicyDisplayGroupSchema],
)
def get_person_policies(
    request: HttpRequest,
    person_id: int,
    chamber_slug: str,
    party_slug: str,
    period_slug: str,
):
    from .views import PersonPoliciesView

    data = PersonPoliciesView().get_context_data(
        person_id, chamber_slug, party_slug, period_slug
    )

    return [PolicyDisplayGroupSchema.from_basic(x) for x in data["collection"]]


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


@api.get("/policy/{policy_id}/report.json")
def get_policy_report_by_id(request: HttpRequest, policy_id: int):
    policy = Policy.objects.get(id=policy_id)
    return PolicyReport.from_policy(policy).model_dump()


@api.get(
    "/policies/{chamber_slug}/{status_slug}/{group_slug}.json",
    response=list[PolicySchema],
)
def get_chamber_status_policies(
    request: HttpRequest, chamber_slug: str, status_slug: str, group_slug: str
):
    if group_slug == "all":
        return Policy.objects.filter(chamber__slug=chamber_slug, status=status_slug)
    else:
        return Policy.objects.filter(
            chamber__slug=chamber_slug, status=status_slug, group__slug=group_slug
        )


@api.get("/policies/reports.json")
def get_all_policy_reports(request: HttpRequest):
    reports = PolicyReport.fetch_multiple([PolicyStatus.ACTIVE, PolicyStatus.CANDIDATE])

    data = [x.model_dump() for x in reports]
    return data


@api.get("/twfy-compatible/popolo/{policy_id}.json", response=PopoloPolicy)
def get_popolo_policy(request: HttpRequest, policy_id: int):
    return PopoloPolicy.from_policy_id(policy_id)
