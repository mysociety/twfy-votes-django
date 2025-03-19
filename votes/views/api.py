import datetime
from typing import Any, Literal

from django.conf import settings
from django.http import HttpRequest

from ninja import ModelSchema, NinjaAPI, Schema
from ninja.security import HttpBearer
from pydantic import BaseModel

from ..consts import PolicyStatus, RebellionPeriodType
from ..models import (
    Agreement,
    AgreementAnnotation,
    Chamber,
    Division,
    DivisionAnnotation,
    DivisionBreakdown,
    DivisionPartyBreakdown,
    DivisionsIsGovBreakdown,
    DivisionTag,
    Motion,
    Organization,
    Person,
    Policy,
    PolicyAgreementLink,
    PolicyComparisonPeriod,
    PolicyDivisionLink,
    PolicyGroup,
    RebellionRate,
    Update,
    Vote,
    VoteAnnotation,
    VoteDistribution,
)
from .helper_models import PairedPolicy, PolicyDisplayGroup, PolicyReport
from .twfy_bridge import PopoloPolicy


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        if token == settings.REFRESH_TOKEN:
            return token


api = NinjaAPI(docs_url="/api", title="TheyWorkForYou Votes API")


class OrganizationSchema(ModelSchema):
    class Meta:
        model = Organization
        fields = "__all__"


class ChamberSchema(ModelSchema):
    class Meta:
        model = Chamber
        fields = "__all__"


class PolicyComparisonPeriodSchema(ModelSchema):
    class Meta:
        model = PolicyComparisonPeriod
        fields = "__all__"


class DivisionTagSchema(ModelSchema):
    class Meta:
        model = DivisionTag
        fields = "__all__"


class MotionSchema(ModelSchema):
    class Meta:
        model = Motion
        fields = "__all__"


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
    url: str

    class Meta:
        model = Division
        fields = "__all__"

    @staticmethod
    def resolve_url(obj: Division) -> str:
        return obj.url()


class AgreementAnnotationSchema(ModelSchema):
    class Meta:
        model = AgreementAnnotation
        fields = "__all__"


class DivisionAnnotationSchema(ModelSchema):
    class Meta:
        model = DivisionAnnotation
        fields = "__all__"


class VoteAnnotationSchema(ModelSchema):
    class Meta:
        model = VoteAnnotation
        fields = "__all__"


class DivisionWithInfoSchema(ModelSchema):
    votes: list[VoteSchema]
    overall_breakdowns: list[DivisionBreakdownSchema]
    party_breakdowns: list[DivisionPartyBreakdownSchema]
    is_gov_breakdowns: list[DivisionsIsGovBreakdownSchema]
    motion: MotionSchema | None
    voting_cluster: dict[str, Any]
    division_annotations: list[DivisionAnnotationSchema]
    vote_annotations: list[VoteAnnotationSchema]
    whip_reports: list[dict[str, Any]]

    @staticmethod
    def resolve_whip_reports(obj: Division):
        df = obj.whip_report_df()
        if df is None:
            return []
        # for columns, drop to lower case and change spaces to underscores
        df.columns = [x.lower().replace(" ", "_") for x in df.columns]
        return df.to_dict(orient="records")

    @staticmethod
    def resolve_voting_cluster(obj: Division):
        di = obj.voting_cluster()
        if di["bespoke"] == "":
            di.pop("bespoke")
        return di

    class Meta:
        model = Division
        fields = "__all__"


class AgreementSchema(ModelSchema):
    agreement_annotations: list[AgreementAnnotationSchema]

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


class RebellionRateSchema(ModelSchema):
    class Meta:
        model = RebellionRate
        fields = "__all__"
        exclude = ["id"]


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


class TriggerSchema(Schema):
    shortcut: str


class PersonPolicySchema(BaseModel):
    person: PersonSchema
    chamber: ChamberSchema
    period: PolicyComparisonPeriodSchema
    party: OrganizationSchema
    policy: PolicySchema
    own_distribution: VoteDistributionSchema
    other_distribution: VoteDistributionSchema
    decision_links_and_votes: dict[str, list[dict[str, Any]]]


@api.post("/webhooks/refresh", include_in_schema=False, auth=AuthBearer())
def refresh_webhook(request: HttpRequest, item: TriggerSchema):
    """
    Trigger a refresh task via webhook
    """

    allowed_refresh = ["refresh_motions_agreements", "refresh_daily"]

    if item.shortcut in allowed_refresh:
        Update.create_task({"shortcut": item.shortcut}, created_via="Webhook")
        return {"status": "success"}
    else:
        return {"status": "failure", "message": "Invalid refresh trigger"}


@api.get(
    "/decisions/division/{chamber_slug}/{date}/{division_number}.json",
    response=DivisionWithInfoSchema,
)
def get_division(
    request: HttpRequest, chamber_slug: str, date: datetime.date, division_number: int
):
    return Division.objects.get(
        chamber_slug=chamber_slug, date=date, division_number=division_number
    ).apply_analysis_override()


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
    "/person/{person_id}/policies/{chamber_slug}/{party_slug}/{period_slug}/{policy_id}.json",
    response=PersonPolicySchema,
)
def get_person_policy(
    request: HttpRequest,
    person_id: int,
    chamber_slug: str,
    party_slug: str,
    period_slug: str,
    policy_id: int,
):
    from .views import PersonPolicyView

    data = PersonPolicyView().get_context_data(
        person_id, chamber_slug, party_slug, period_slug, policy_id
    )

    data.pop("view")

    data["decision_links_and_votes"] = {
        x: y.to_dict(orient="records")
        for x, y in data["decision_links_and_votes"].items()
    }

    print(data)

    return data


@api.get(
    "/decisions/agreement/{chamber_slug}/{date}/{decision_ref}.json",
    response=AgreementSchema,
)
def get_agreement(
    request: HttpRequest, chamber_slug: str, date: datetime.date, decision_ref: str
):
    return Agreement.objects.get(
        chamber_slug=chamber_slug, date=date, decision_ref=decision_ref
    ).apply_analysis_override()


@api.get("/decisions/commons_api_source.json", response=list[DivisionSchema])
def commons_api_source(request: HttpRequest):
    return Division.objects.filter(division_info_source="commons_api")


@api.get("/decisions/{chamber_slug}/{year}.json", response=list[DivisionSchema])
def get_divisions_by_year(request: HttpRequest, chamber_slug: str, year: int):
    return [
        x.apply_analysis_override()
        for x in Division.objects.filter(chamber_slug=chamber_slug, date__year=year)
    ]


@api.get("/decisions/{chamber_slug}/{year}/{month}.json", response=list[DivisionSchema])
def get_divisions_by_month(
    request: HttpRequest, chamber_slug: str, year: int, month: int
):
    return [
        x.apply_analysis_override()
        for x in Division.objects.filter(
            chamber_slug=chamber_slug, date__year=year, date__month=month
        )
    ]


@api.get("/policies.json", response=list[PolicySchema])
def get_policies(request: HttpRequest):
    return Policy.objects.all().prefetch_related(
        "groups",
        "division_links",
        "division_links__decision",
        "agreement_links",
        "agreement_links__decision",
    )


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


@api.get(
    "/party_alignment/{period_slug}/{period_number}.json",
    response=list[RebellionRateSchema],
)
def get_party_alignment_all(
    request: HttpRequest, period_slug: Literal["year", "period"], period_number: int
):
    match period_slug:
        case "year":
            period_int = RebellionPeriodType.YEAR
        case "all_time":
            period_int = RebellionPeriodType.ALLTIME
        case "period":
            period_int = RebellionPeriodType.PERIOD
        case _:
            raise ValueError(f"Unknown period slug {period_slug}")

    return RebellionRate.objects.filter(
        period_type=period_int, period_number=period_number
    ).order_by("person_id")


@api.get(
    "/party_alignment/person/{person_id}/{period_slug}.json",
    response=list[RebellionRateSchema],
)
def get_party_alignment(
    request: HttpRequest,
    person_id: str,
    period_slug: Literal["all_time", "year", "period"],
):
    match period_slug:
        case "year":
            period_int = RebellionPeriodType.YEAR
        case "all_time":
            period_int = RebellionPeriodType.ALLTIME
        case "period":
            period_int = RebellionPeriodType.PERIOD
        case _:
            raise ValueError(f"Unknown period slug {period_slug}")

    return RebellionRate.objects.filter(
        period_type=period_int, person_id=person_id
    ).order_by("period_number")
