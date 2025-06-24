import re
from datetime import date
from typing import Any, Optional

from django.urls import URLPattern, path, register_converter
from django.views.generic import View

from .views.api import api
from .views.opengraph_views import (
    AgreementOpenGraphImageView,
    DecisionsListOpenGraphImageView,
    DivisionOpenGraphImageView,
    GeneralOpenGraphImageView,
    MarkdownOpenGraphImageView,
    PersonOpenGraphImageView,
    PolicyOpenGraphImageView,
    StatementsListOpenGraphImageView,
    TagOpenGraphImageView,
)
from .views.views import (
    AgreementPageView,
    DataView,
    DecisionsListMonthPageView,
    DecisionsListPageView,
    DecisionsPageView,
    DivisionPageView,
    DuckDBDownloadView,
    FormsView,
    HomePageView,
    MarkdownView,
    PeoplePageView,
    PersonPageView,
    PersonPoliciesView,
    PersonPolicyView,
    PersonStatementsPageView,
    PersonVotesPageView,
    PoliciesPageView,
    PoliciesReportsPageView,
    PolicyCollectionPageView,
    PolicyPageView,
    PolicyReportPageView,
    StatementPageView,
    StatementsListMonthPageView,
    StatementsListPageView,
    StatementsPageView,
    TagListView,
    TagsHomeView,
)


class ISODateConverter:
    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        return date.fromisoformat(value)

    def to_url(self, value: date) -> str:
        return value.isoformat()


class StringNotJson:
    """
    checks if it's a lowercase string that doesn't end in .json
    """

    regex = r"[a-z0-9.]+(?<!\.json)"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value


register_converter(ISODateConverter, "date")
register_converter(StringNotJson, "str_not_json")


def fast_path(
    route: str,
    view: type[View],
    kwargs: Optional[dict[str, Any]] = None,
    name: Optional[str] = None,
) -> URLPattern:
    """
    Quick helper function that adapts fastapi style routes to django style routes.
    Prefer as it highlights the variables in the IDE, and the type hint is
    the same way around as elsewhere in python.
    """
    if not name:
        raise ValueError("Name is required")

    # need to convert any {year:int} to <int:year>
    route = re.sub(r"{(\w+):(\w+)}", r"<\2:\1>", route)

    # and any just plain {year} to <year>
    route = re.sub(r"{(\w+)}", r"<\1>", route)

    return path(route, view.as_view(), name=name, kwargs=kwargs or {})


urlpatterns = [
    fast_path("", HomePageView, name="home"),
    fast_path("people/{filter:slug}", PeoplePageView, name="people"),
    fast_path("person/{person_id:int}", PersonPageView, name="person"),
    fast_path(
        "person/{person_id:int}/votes/{year:str}",
        PersonVotesPageView,
        name="person_votes",
    ),
    fast_path(
        "person/{person_id:int}/statements",
        PersonStatementsPageView,
        name="person_statements",
    ),
    fast_path("decisions", DecisionsPageView, name="decisions"),
    fast_path("tags", TagsHomeView, name="tag_home"),
    fast_path("tags/{tag_type:slug}", TagsHomeView, name="tag_home"),
    fast_path("tags/{tag_type:slug}/{tag_slug:slug}", TagListView, name="tag"),
    fast_path(
        "decisions/division/{chamber_slug:str}/{decision_date:date}/{decision_num:int}",
        DivisionPageView,
        name="division",
    ),
    fast_path(
        "decisions/agreement/{chamber_slug:str}/{decision_date:date}/{decision_ref:str_not_json}",
        AgreementPageView,
        name="agreement",
    ),
    fast_path(
        "statement/{chamber_slug:str}/{statement_date:date}/{statement_slug:slug}",
        StatementPageView,
        name="statement",
    ),
    fast_path("statements", StatementsPageView, name="statements"),
    fast_path(
        "statements/{chamber_slug:str}/{year:int}",
        StatementsListPageView,
        name="statements_list",
    ),
    fast_path(
        "statements/{chamber_slug:str}/{year:int}/{month:int}",
        StatementsListMonthPageView,
        name="statements_list_month",
    ),
    fast_path(
        "decisions/{chamber_slug:str}/{year:int}",
        DecisionsListPageView,
        name="decisions_list",
    ),
    fast_path(
        "decisions/{chamber_slug:str}/{year:int}/{month:int}",
        DecisionsListMonthPageView,
        name="decisions_list_month",
    ),
    fast_path(
        "policies/reports",
        PoliciesReportsPageView,
        name="policies_reports",
    ),
    fast_path("policies", PoliciesPageView, name="policies"),
    fast_path("policy/{policy_id:int}", PolicyPageView, name="policy"),
    fast_path(
        "policy/{policy_id:int}/report",
        PolicyReportPageView,
        name="policy_reports",
    ),
    fast_path(
        "policies/{chamber_slug:str}/{status_slug:str}/{group_slug:slug}",
        PolicyCollectionPageView,
        name="policy_collection",
    ),
    fast_path(
        "person/{person_id:int}/policies/{chamber_slug:slug}/{party_slug:slug}/{period_slug:slug}",
        PersonPoliciesView,
        name="person_policy",
    ),
    fast_path(
        "person/{person_id:int}/policies/{chamber_slug:slug}/{party_slug:slug}/{period_slug:slug}/{policy_id:int}",
        PersonPolicyView,
        name="person_policy_solo",
    ),
    fast_path(
        "submit/{form_slug:slug}/{decision_id:int}",
        FormsView,
        name="forms",
    ),
    fast_path(
        "submit/statement",
        FormsView,
        kwargs={"form_slug": "statement", "decision_id": 0},
        name="statement_form",
    ),
    fast_path("help/{markdown_slug:slug}", MarkdownView, name="help"),
    fast_path("data", DataView, name="data"),
    fast_path(
        "opengraph/division/{division_id:int}",
        DivisionOpenGraphImageView,
        name="division_opengraph_image",
    ),
    fast_path(
        "opengraph/agreement/{agreement_id:int}",
        AgreementOpenGraphImageView,
        name="agreement_opengraph_image",
    ),
    fast_path(
        "opengraph/misc/{page_slug:slug}",
        GeneralOpenGraphImageView,
        name="general_opengraph_image",
    ),
    fast_path(
        "opengraph/person/{person_id:int}",
        PersonOpenGraphImageView,
        name="person_opengraph_image",
    ),
    fast_path(
        "opengraph/policy/{policy_id:int}",
        PolicyOpenGraphImageView,
        name="policy_opengraph_image",
    ),
    fast_path(
        "opengraph/tag/{tag_type:slug}/{tag_slug:slug}",
        TagOpenGraphImageView,
        name="tag_opengraph_image",
    ),
    fast_path(
        "opengraph/markdown/{markdown_slug:slug}",
        MarkdownOpenGraphImageView,
        name="markdown_opengraph_image",
    ),
    fast_path(
        "opengraph/decisions/{chamber_slug:slug}/{year:int}",
        DecisionsListOpenGraphImageView,
        name="decisions_list_opengraph_image",
    ),
    fast_path(
        "opengraph/decisions/{chamber_slug:slug}/{year:int}/{month:int}",
        DecisionsListOpenGraphImageView,
        name="decisions_list_month_opengraph_image",
    ),
    fast_path("data/duck", DuckDBDownloadView, name="duckdb_download"),
    fast_path(
        "opengraph/statements/{chamber_slug:slug}/{year:int}",
        StatementsListOpenGraphImageView,
        name="statements_list_opengraph_image",
    ),
    fast_path(
        "opengraph/statements/{chamber_slug:slug}/{year:int}/{month:int}",
        StatementsListOpenGraphImageView,
        name="statements_list_month_opengraph_image",
    ),
    path("", api.urls),
]
