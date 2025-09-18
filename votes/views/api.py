import datetime
from typing import Any, Literal

from django.conf import settings
from django.http import HttpRequest, HttpResponse

import pandas as pd
from ninja import ModelSchema, NinjaAPI, Schema
from ninja.security import HttpBearer
from pydantic import BaseModel

from ..consts import PolicyStatus, RebellionPeriodType
from ..models import (
    Agreement,
    AgreementAnnotation,
    Chamber,
    DecisionTag,
    Division,
    DivisionAnnotation,
    DivisionBreakdown,
    DivisionPartyBreakdown,
    DivisionsIsGovBreakdown,
    Motion,
    Organization,
    Person,
    Policy,
    PolicyAgreementLink,
    PolicyComparisonPeriod,
    PolicyDivisionLink,
    PolicyGroup,
    RebellionRate,
    Signature,
    Statement,
    Update,
    Vote,
    VoteAnnotation,
    VoteDistribution,
)
from .auth import can_view_draft_content
from .helper_models import PairedPolicy, PolicyDisplayGroup, PolicyReport
from .twfy_bridge import PopoloPolicy


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        if token == settings.REFRESH_TOKEN:
            return token


api = NinjaAPI(docs_url="/api", title="TheyWorkForYou Votes API")


class DecisionTagSchema(ModelSchema):
    class Meta:
        model = DecisionTag
        fields = "__all__"


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
    vote: str
    effective_vote: str
    party: str

    @staticmethod
    def resolve_vote(obj: Vote):
        return obj.vote.name.title()

    @staticmethod
    def resolve_effective_vote(obj: Vote):
        return obj.effective_vote.name.title()

    @staticmethod
    def resolve_party(obj: Vote):
        return obj.membership.party.slug

    class Meta:
        model = Vote
        exclude = ["id", "vote", "effective_vote"]
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
    legislation: DecisionTagSchema | None
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
    def resolve_legislation(obj: Division):
        legislation = obj.legislation_tag()
        if legislation is None:
            return None
        return legislation

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


class PolicyWithFreeVoteListSchema(PolicySchema):
    """Extended Policy schema that includes free vote counts for specific endpoints"""

    free_vote_parties: list[str]

    @staticmethod
    def resolve_free_vote_parties(obj: Policy):
        return obj.get_free_vote_parties()


class RebellionRateSchema(ModelSchema):
    class Meta:
        model = RebellionRate
        fields = "__all__"
        exclude = ["id"]


class SignatureSchema(ModelSchema):
    person: PersonSchema
    withdrawn_status: str

    @staticmethod
    def resolve_withdrawn_status(obj: Signature) -> str:
        return obj.withdrawn_status() or "-"

    class Meta:
        model = Signature
        fields = "__all__"


class StatementSchema(ModelSchema):
    signatures: list[SignatureSchema]
    tags: list[DecisionTagSchema]
    url: str
    nice_title: str
    type_display: str

    @staticmethod
    def resolve_url(obj: Statement) -> str:
        return obj.page_url()

    @staticmethod
    def resolve_nice_title(obj: Statement) -> str:
        return obj.nice_title()

    @staticmethod
    def resolve_type_display(obj: Statement) -> str:
        return obj.type_display()

    class Meta:
        model = Statement
        fields = "__all__"


class TagWithDecisionsSchema(ModelSchema):
    divisions: list[DivisionSchema]
    agreements: list[AgreementSchema]
    statements: list[StatementSchema]

    class Meta:
        model = DecisionTag
        fields = "__all__"


class StatementListSchema(ModelSchema):
    url: str
    nice_title: str
    type_display: str
    signature_count: int

    @staticmethod
    def resolve_url(obj: Statement) -> str:
        return obj.page_url()

    @staticmethod
    def resolve_nice_title(obj: Statement) -> str:
        return obj.nice_title()

    @staticmethod
    def resolve_type_display(obj: Statement) -> str:
        return obj.type_display()

    @staticmethod
    def resolve_signature_count(obj: Statement) -> int:
        # Use the annotated signature_count field from the queryset
        return getattr(obj, "signature_count", 0)

    class Meta:
        model = Statement
        fields = [
            "id",
            "key",
            "chamber_slug",
            "title",
            "slug",
            "statement_text",
            "original_id",
            "chamber",
            "info_source",
            "date",
            "type",
            "extra_info",
            "url",
        ]


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


@api.get("/tags.json", response=list[DecisionTagSchema])
def tags_api(request: HttpRequest):
    return DecisionTag.objects.all()


@api.get("/tags/{tag_type}.json", response=list[DecisionTagSchema])
def single_type_tag_api(request: HttpRequest, tag_type: str):
    return DecisionTag.objects.filter(tag_type=tag_type)


@api.get("/tags/{tag_type}/{tag}.json", response=TagWithDecisionsSchema)
def tag_to_api(request: HttpRequest, tag_type: str, tag: str):
    return (
        DecisionTag.objects.filter(tag_type=tag_type, slug=tag)
        .prefetch_related(
            "divisions",
            "divisions__tags",
            "divisions__chamber",
            "divisions__motion",
            "divisions__votes",
            "divisions__votes__person",
            "divisions__overall_breakdowns",
            "divisions__party_breakdowns",
            "divisions__is_gov_breakdowns",
            "agreements",
            "agreements__tags",
            "agreements__chamber",
            "agreements__motion",
            "statements",
            "statements__tags",
            "statements__chamber",
            "statements__signatures",
            "statements__signatures__person",
        )
        .first()
    )


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
    division = (
        Division.objects.filter(
            chamber_slug=chamber_slug, date=date, division_number=division_number
        )
        .prefetch_related(
            "votes", "votes__person", "votes__membership", "votes__membership__party"
        )
        .first()
    )

    if division is None:
        raise ValueError(
            f"Division not found for {chamber_slug} {date} {division_number}"
        )
    return division.apply_analysis_override()


@api.get(
    "/decisions/division/{chamber_slug}/{date}/{division_number}/voting_list.csv",
)
def get_division_csv(
    request: HttpRequest, chamber_slug: str, date: datetime.date, division_number: int
):
    """
    Export division voting information as a CSV file using pandas for efficient handling.
    """
    division = (
        Division.objects.filter(
            chamber_slug=chamber_slug, date=date, division_number=division_number
        )
        .prefetch_related(
            "votes", "votes__person", "votes__membership", "votes__membership__party"
        )
        .first()
    )

    if division is None:
        raise ValueError(
            f"Division not found for {chamber_slug} {date} {division_number}"
        )

    # Apply any analysis overrides
    division = division.apply_analysis_override()

    # Create a list of dictionaries for pandas DataFrame
    vote_data = [
        {
            "person_id": vote.person.id,
            "name": vote.person.name,
            "party_name": (
                vote.membership.party.name
                if vote.membership and vote.membership.party
                else ""
            ),
            "party_slug": (
                vote.membership.party.slug
                if vote.membership and vote.membership.party
                else ""
            ),
            "vote": vote.vote.name.title(),
            "effective_vote": vote.effective_vote.name.title(),
            "is_government": "Yes" if vote.is_gov else "No",
            "division_name": division.division_name,
            "division_date": division.date,
            "division_number": division.division_number,
            "chamber": division.chamber_slug,
        }
        for vote in division.votes.all()
    ]

    # Create DataFrame from the data
    df = pd.DataFrame(vote_data)

    # Create a CSV response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="voting-list-{chamber_slug}-{date}-{division_number}.csv"'
    )

    # Use pandas to write the CSV to the response
    csv_data = df.to_csv(index=False)
    response.write(csv_data)

    return response


@api.get("/people/{people_option}.json", response=list[PersonSchema])
def get_people(request: HttpRequest, people_option: Literal["current", "all"]):
    if people_option == "current":
        query = Person.current()
    else:
        query = Person.objects.all()

    return query


@api.get("/person/{person_id}.json", response=PersonSchema)
def get_person(request: HttpRequest, person_id: int):
    return Person.objects.get(id=person_id)


@api.get("/person/{person_id}/votes.json", response=PersonWithVoteSchema)
def get_person_with_votes(request: HttpRequest, person_id: int):
    return Person.objects.get(id=person_id)


@api.get("/person/{person_id}/statements.json", response=dict)
def get_person_statements(request: HttpRequest, person_id: int):
    """
    Get statements data for a person, returning the statements dataframe as JSON
    """
    from .views import PersonStatementsPageView

    data = PersonStatementsPageView().get_context_data(person_id)

    # Convert the statements DataFrame to records
    statements_data = data["statements_df"].to_dict(orient="records")

    return {
        "person": PersonSchema.model_validate(data["person"]).model_dump(),
        "statements": statements_data,
    }


@api.get(
    "/statement/{chamber_slug}/{statement_date}/{slug:statement_slug}.json",
    response=StatementSchema,
)
def get_statement(
    request: HttpRequest,
    chamber_slug: str,
    statement_date: datetime.date,
    statement_slug: str,
):
    """
    Get statement data with all signatures
    """

    statement = (
        Statement.objects.filter(
            chamber__slug=chamber_slug,
            date=statement_date,
            slug=statement_slug,
        )
        .prefetch_related(
            "signatures",
            "signatures__person",
            "tags",
        )
        .first()
    )

    if not statement:
        raise ValueError(f"Statement not found: {statement_slug}")

    return statement


@api.get("/statements/{chamber_slug}/{year}.json", response=list[StatementListSchema])
def get_statements_by_year(request: HttpRequest, chamber_slug: str, year: int):
    from django.db.models import Count

    return (
        Statement.objects.filter(chamber_slug=chamber_slug, date__year=year)
        .annotate(signature_count=Count("signatures"))
        .select_related("chamber")
        .order_by("-date", "title")
    )


@api.get(
    "/statements/{chamber_slug}/{int:year}/{int:month}.json",
    response=list[StatementListSchema],
)
def get_statements_by_month(
    request: HttpRequest, chamber_slug: str, year: int, month: int
):
    from django.db.models import Count

    return (
        Statement.objects.filter(
            chamber_slug=chamber_slug, date__year=year, date__month=month
        )
        .annotate(signature_count=Count("signatures"))
        .select_related("chamber")
        .order_by("-date", "title")
    )


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


@api.get("/policies.json", response=list[PolicyWithFreeVoteListSchema])
def get_policies(request: HttpRequest):
    policies_query = Policy.objects.all().prefetch_related(
        "groups",
        "division_links",
        "division_links__decision",
        "division_links__decision__whip_reports",
        "division_links__decision__whip_reports__party",
        "division_links__decision__tags",
        "agreement_links",
        "agreement_links__decision",
        "agreement_links__decision__tags",
    )

    if not can_view_draft_content(request.user):
        policies_query = policies_query.filter(
            status__in=[PolicyStatus.ACTIVE, PolicyStatus.CANDIDATE]
        )

    return policies_query


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
        query = Policy.objects.filter(chamber__slug=chamber_slug, status=status_slug)
    else:
        query = Policy.objects.filter(
            chamber__slug=chamber_slug, status=status_slug, group__slug=group_slug
        )
    return query.prefetch_related(
        "groups",
        "division_links",
        "division_links__decision",
        "division_links__decision__tags",
        "agreement_links",
        "agreement_links__decision",
        "agreement_links__decision__tags",
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
