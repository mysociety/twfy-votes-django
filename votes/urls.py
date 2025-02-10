import re
from datetime import date
from typing import Any, Optional

from django.urls import URLPattern, path, register_converter
from django.views.generic import View

from .views import views
from .views.api import api


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

    return path(route, view.as_view(), name=name)


urlpatterns = [
    fast_path("", views.HomePageView, name="home"),
    fast_path("people/{filter:slug}", views.PeoplePageView, name="people"),
    fast_path("person/{person_id:int}", views.PersonPageView, name="person"),
    fast_path(
        "person/{person_id:int}/votes/{year:str}",
        views.PersonVotesPageView,
        name="person_votes",
    ),
    fast_path("decisions", views.DecisionsPageView, name="decisions"),
    fast_path(
        "decisions/division/{chamber_slug:str}/{decision_date:date}/{decision_num:int}",
        views.DivisionPageView,
        name="division",
    ),
    fast_path(
        "decisions/agreement/{chamber_slug:str}/{decision_date:date}/{decision_ref:str_not_json}",
        views.AgreementPageView,
        name="agreement",
    ),
    fast_path(
        "decisions/{chamber_slug:str}/{year:int}",
        views.DecisionsListPageView,
        name="decisions_list",
    ),
    fast_path(
        "decisions/{chamber_slug:str}/{year:int}/{month:int}",
        views.DecisionsListMonthPageView,
        name="decisions_list_month",
    ),
    fast_path(
        "policies/reports",
        views.PoliciesReportsPageView,
        name="policies_reports",
    ),
    fast_path("policies", views.PoliciesPageView, name="policies"),
    fast_path("policy/{policy_id:int}", views.PolicyPageView, name="policy"),
    fast_path(
        "policy/{policy_id:int}/report",
        views.PolicyReportPageView,
        name="policy_reports",
    ),
    fast_path(
        "policies/{chamber_slug:str}/{status_slug:str}/{group_slug:slug}",
        views.PolicyCollectionPageView,
        name="policy_collection",
    ),
    fast_path(
        "person/{person_id:int}/policies/{chamber_slug:slug}/{party_slug:slug}/{period_slug:slug}",
        views.PersonPoliciesView,
        name="person_policy",
    ),
    fast_path(
        "person/{person_id:int}/policies/{chamber_slug:slug}/{party_slug:slug}/{period_slug:slug}/{policy_id:int}",
        views.PersonPolicyView,
        name="person_policy_solo",
    ),
    fast_path(
        "submit/{form_slug:slug}/{decision_id:int}",
        views.FormsView,
        name="forms",
    ),
    fast_path("help/{markdown_slug:slug}", views.MarkdownView, name="help"),
    fast_path("data", views.DataView, name="data"),
    path("", api.urls),
]
