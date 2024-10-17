import calendar
import datetime
from typing import Literal

from django.views.generic import TemplateView

from twfy_votes.helpers.routes import RouteApp

from ..consts import PolicyStatus
from ..models.decisions import Agreement, Chamber, Division, Policy, Vote
from ..models.people import Person
from .helper_models import DivisionSearch
from .mixins import TitleMixin

app = RouteApp(app_name="votes")


@app.route("", name="home")
class HomePageView(TitleMixin, TemplateView):
    page_title = ""
    template_name = "votes/home.html"


@app.route("people/{filter:str}", name="people")
class PeoplePageView(TitleMixin, TemplateView):
    page_title = "People"
    template_name = "votes/people.html"

    def get_context_data(self, filter: Literal["all", "current"], **kwargs):
        context = super().get_context_data(**kwargs)
        if filter == "all":
            context["people"] = Person.objects.all()
        elif filter == "current":
            context["people"] = Person.current()
        return context


@app.route("person/{person_id:int}", name="person")
class PersonPageView(TitleMixin, TemplateView):
    page_title = "Person"
    template_name = "votes/person.html"

    def get_context_data(self, person_id: int, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person"] = Person.objects.get(id=person_id)
        return context


@app.route("person/{person_id:int}/votes", name="person_votes")
class PersonVotesPageView(TitleMixin, TemplateView):
    page_title = "Person Votes"
    template_name = "votes/person_votes.html"

    def get_context_data(self, person_id: int, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person"] = Person.objects.get(id=person_id)
        context["votes"] = Vote.objects.filter(person_id=person_id)

        return context


@app.route("decisions", name="decisions")
class DecisionsPageView(TitleMixin, TemplateView):
    page_title = "Decisions"
    template_name = "votes/decisions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chambers"] = Chamber.objects.all()
        return context


@app.route(
    "decision/division/{chamber_slug:str}/{decision_date:date}/{decision_num:int}",
    name="division",
)
class DivisionPageView(TitleMixin, TemplateView):
    page_title = "Division"
    template_name = "votes/decision.html"

    def get_context_data(
        self,
        chamber_slug: str,
        decision_date: datetime.date,
        decision_num: int,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)
        context["decision"] = Division.objects.get(
            chamber__slug=chamber_slug, date=decision_date, division_number=decision_num
        )
        return context


@app.route(
    "decision/agreement/{chamber_slug:str}/{decision_date:date}/{decision_ref:str}",
    name="agreement",
)
class AgreementPageView(TitleMixin, TemplateView):
    page_title = "Agreement"
    template_name = "votes/agreement.html"

    def get_context_data(
        self,
        chamber_slug: str,
        decision_date: datetime.date,
        decision_ref: str,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)
        context["agreement"] = Agreement.objects.get(
            chamber__slug=chamber_slug, date=decision_date, reference=decision_ref
        )
        return context


@app.route("decisions/{chamber_slug:str}/{year:int}", name="decisions_list")
class DecisionsListPageView(TitleMixin, TemplateView):
    page_title = "Decisions List"
    template_name = "votes/decisions_list.html"

    def decision_search(
        self, chamber: Chamber, start_date: datetime.date, end_date: datetime.date
    ):
        relevent_divisions = Division.objects.filter(
            chamber=chamber, date__range=(start_date, end_date)
        )
        relevant_agreements = Agreement.objects.filter(
            chamber=chamber, date__range=(start_date, end_date)
        )
        decisions = list(relevent_divisions) + list(relevant_agreements)
        decisions.sort(key=lambda x: x.date)
        return DivisionSearch(
            start_date=start_date,
            end_date=end_date,
            chamber=chamber,
            decisions=decisions,
        )

    def get_context_data(self, chamber_slug: str, year: int, **kwargs):
        context = super().get_context_data(*kwargs)
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        chamber = Chamber.objects.get(slug=chamber_slug)

        search = self.decision_search(chamber, year_start, year_end)
        context["search"] = search

        return context


@app.route(
    "decisions/{chamber_slug:str}/{year:int}/{month:int}", name="decisions_list_month"
)
class DecisionsListMonthPageView(DecisionsListPageView):
    page_title = "Decisions List Month"
    template_name = "votes/decisions_list_month.html"

    def get_context_data(self, chamber_slug: str, year: int, month: int, **kwargs):
        context = super(DecisionsListPageView, self).get_context_data(**kwargs)
        month_start = datetime.date(year, month, 1)
        month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])

        chamber = Chamber.objects.get(slug=chamber_slug)
        search = self.decision_search(chamber, month_start, month_end)
        context["search"] = search

        return context


@app.route("policies", name="policies")
class PoliciesPageView(TitleMixin, TemplateView):
    page_title = "Policies"
    template_name = "votes/policies.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # get chambers
        context["chambers"] = Chamber.objects.all()
        # get policy statuses
        context["statuses"] = PolicyStatus
        return context


@app.route("policies/reports", name="policies_reports")
class PoliciesReportsPageView(TitleMixin, TemplateView):
    page_title = "Policies Reports"
    template_name = "votes/policies_reports.html"


@app.route("policy/{policy_id:int}", name="policy")
class PolicyPageView(TitleMixin, TemplateView):
    page_title = "Policy"
    template_name = "votes/policy.html"

    def get_context_data(self, policy_id: int, **kwargs):
        context = super().get_context_data(**kwargs)
        context["policy"] = Policy.objects.get(id=policy_id)
        return context


@app.route("policy/{policy_id:int}/report", name="policy_reports")
class PolicyReportPageView(TitleMixin, TemplateView):
    page_title = "Policy Reports"
    template_name = "votes/policy_reports.html"

    def get_context_data(self, policy_id: int, **kwargs):
        context = super().get_context_data(**kwargs)
        context["policy"] = Policy.objects.get(id=policy_id)
        return context


@app.route(
    "policies/{chamber_slug:str}/{status_slug:str}/{group_slug:str}",
    name="policy_collection",
)
class PolicyCollectionPageView(TitleMixin, TemplateView):
    page_title = "Policy Collection"
    template_name = "votes/policy_collection.html"

    def get_context_data(
        self, chamber_slug: str, status_slug: str, group_slug: str, **kwargs
    ):
        context = super().get_context_data(**kwargs)
        context["policies"] = Policy.objects.filter(
            chamber__slug=chamber_slug, status=status_slug, groups=group_slug
        )
        return context


@app.route(
    "policy/{policy_id:int}/{person_id:int}/{party_slug:str}", name="policy_people"
)
class PolicyPeoplePageView(TitleMixin, TemplateView):
    page_title = "Policy People"
    template_name = "votes/policy_people.html"

    def get_context_data(
        self, policy_id: int, person_id: int, party_slug: str, **kwargs
    ):
        context = super().get_context_data(**kwargs)
        context["policy"] = Policy.objects.get(id=policy_id)
        context["person"] = Person.objects.get(id=person_id)
        context["party"] = party_slug
        # needs extra stuff to get the real details
        return context
