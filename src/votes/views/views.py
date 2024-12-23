from __future__ import annotations

import calendar
import datetime
import re
from pathlib import Path
from typing import Literal

from django.http import Http404, HttpRequest
from django.shortcuts import redirect
from django.template import Context, Template
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView

import markdown
import pandas as pd
from bs4 import BeautifulSoup

from twfy_votes.helpers.routes import RouteApp

from ..consts import (
    ChamberSlug,
    PermissionGroupSlug,
    PolicyDirection,
    PolicyStatus,
    StrVotePosition,
    VotePosition,
)
from ..forms import (
    AgreementAnnotationForm,
    DivisionAnnotationForm,
    OpenRepAnnotationForm,
    RepAnnotationForm,
    RepWhipForm,
    WhipForm,
)
from ..models import (
    Agreement,
    Chamber,
    Division,
    Membership,
    Organization,
    Person,
    Policy,
    PolicyAgreementLink,
    PolicyComparisonPeriod,
    PolicyDivisionLink,
    UrlColumn,
    UserPersonLink,
    Vote,
)
from .auth import can_view_draft_content, super_users_or_group
from .helper_models import (
    ChamberPolicyGroup,
    DivisionSearch,
    PolicyCollection,
    PolicyReport,
)
from .mixins import TitleMixin

app = RouteApp(app_name="votes")


@app.route("submit/{form_slug:slug}/{decision_id:int}", name="forms")
class FormsView(TemplateView):
    template_name = "votes/forms.html"

    def get_form_model(self, form_slug: str):
        match form_slug:
            case "whip":
                return WhipForm
            case "rep_whip":
                return RepWhipForm
            case "division_annotation":
                return DivisionAnnotationForm
            case "agreement_annotation":
                return AgreementAnnotationForm
            case "open_rep_annotation":
                return OpenRepAnnotationForm
            case "rep_annotation":
                return RepAnnotationForm
            case _:
                raise Http404("Form not found")

    def user_has_permission(self, form_slug: str):
        match form_slug:
            case "whip":
                return super_users_or_group(
                    self.request.user, PermissionGroupSlug.CAN_REPORT_WHIP
                )
            case "rep_whip":
                return super_users_or_group(
                    self.request.user, PermissionGroupSlug.CAN_REPORT_SELF_WHIP
                )
            case "division_annotation":
                return super_users_or_group(
                    self.request.user, PermissionGroupSlug.CAN_ADD_ANNOTATIONS
                )
            case "agreement_annotation":
                return super_users_or_group(
                    self.request.user, PermissionGroupSlug.CAN_ADD_ANNOTATIONS
                )
            case "open_rep_annotation":
                return super_users_or_group(
                    self.request.user, PermissionGroupSlug.CAN_ADD_ANNOTATIONS
                )
            case "rep_annotation":
                if not self.request.user.is_authenticated:
                    return False
                link = UserPersonLink.objects.get(user=self.request.user)
                if not link:
                    return False
                return super_users_or_group(
                    self.request.user, PermissionGroupSlug.CAN_ADD_SELF_ANNOTATIONS
                )
            case _:
                return False

    def get_decision_instance(self, form_slug: str, decision_id: int):
        match form_slug:
            case "agreement_annotation":
                agreement = Agreement.objects.get(id=decision_id)
                return agreement
            case _:
                division = Division.objects.get(id=decision_id)
                return division

    def post(self, request: HttpRequest, form_slug: str, decision_id: int, **kwargs):
        form_model = self.get_form_model(form_slug)
        decision = self.get_decision_instance(form_slug, decision_id)
        if not self.user_has_permission(form_slug):
            raise Http404(f"User does not have permission to save form {form_slug}")
        form = form_model(request.POST)
        if form.is_valid():
            form.save(request, decision_id)

            return redirect(decision.url())

        else:
            # return the form with errors
            return self.render_to_response({"form": form, "decision": decision})

    def get_context_data(self, form_slug: str, decision_id: int, **kwargs):
        # decision_int could be division_id or agreement_id
        form_model = self.get_form_model(form_slug)
        if not self.user_has_permission(form_slug):
            raise Http404(f"User does not have permission to access form {form_slug}")

        decision = self.get_decision_instance(form_slug, decision_id)

        form = form_model.from_decision_id(decision_id)

        return {"form": form, "decision": decision}


@app.route("help/{markdown_slug:slug}", name="help")
class MarkdownView(TemplateView):
    """
    View that accepts a markdown slug and renders the markdown file
    with the given slug in the template.
    """

    template_name = "votes/markdown.html"

    def get_markdown_context(self, **kwargs) -> dict:
        """
        Override this method to add extra context to feed to the markdown.
        """
        return {}

    def get_context_data(self, **kwargs):
        """
        Given a markdown slug, fetch the file from caps/templates/caps/markdown/{slug}.md
        This is a jekyll style markdown file, with a yaml header and markdown body.
        The yaml header is parsed and used to populate the template context.
        """
        context = super().get_context_data(**kwargs)

        markdown_slug = kwargs.get("markdown_slug")
        if markdown_slug is None:
            raise Http404
        # sanitise the slug to prevent directory traversal
        markdown_slug = re.sub(r"[^a-zA-Z0-9_-]", "", markdown_slug)
        template_path = Path("src", "votes", "markdown/{}.md".format(markdown_slug))
        markdown_body = template_path.read_text()

        # Extract the markdown H1 header to use as the page title, and remove it from the markdown_body
        lines = markdown_body.splitlines()
        h1_header = lines[0]
        assert h1_header.startswith(
            "# "
        ), "Markdown file should start with an H1 header '# title'"
        markdown_body = "\n".join(lines[1:])
        context["page_title"] = h1_header[2:]

        markdown_content = markdown.markdown(markdown_body, extensions=["toc"])

        markdown_context = Context(self.get_markdown_context(**kwargs))

        # we want to run the markdown_content through a basic django template so that any urls, etc are expanded
        markdown_content = Template(markdown_content).render(markdown_context)

        # there are ids assigned to each header by the TOC extention, extract these so we can put them in the sidebar
        soup = BeautifulSoup(markdown_content, "html.parser")
        headers = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        header_links = []
        last_item = {1: None, 2: None, 3: None, 4: None, 5: None, 6: None}

        for header in headers:
            header_item = {
                "level": int(header.name[1]),
                "text": header.text,
                "id": header.attrs["id"],
                "parent": None,
            }
            current_level = header_item["level"]
            last_item[current_level] = header_item["id"]
            if current_level > 1:
                header_item["parent"] = last_item[current_level - 1]
            header_links.append(header_item)

        # re-arrange the headers into a tree
        for header in header_links:
            header["children"] = [
                h for h in header_links if h["parent"] == header["id"]
            ]

        # remove anything below h3 and that will now be a child from top level
        header_links = [
            h for h in header_links if h["level"] <= 3 and h["parent"] is None
        ]

        context["body"] = mark_safe(markdown_content)
        context["header_links"] = header_links
        context["show_menu"] = True
        return context


@app.route("data", name="data")
class DataView(TitleMixin, TemplateView):
    page_title = "Data"
    template_name = "votes/data.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # we want the last three votes for each chamber

        data = {
            "clusters_labelled": "Parliamentary dynamics vote clusters, by division.",
            "division_with_counts": "Division information with basic counts",
            "divisions_gov_with_counts": "Division breakdowns split by government/opposition",
            "divisions_party_with_counts": "Division breakdowns split by party",
            "organization": "Party ids and names",
            "per_person_party_diff_all_time": "Voting alignment scores all time",
            "per_person_party_diff_period": "Voting alignment scores by rolling period",
            "per_person_party_diff_year": "Voting alignment scores by year",
            "policy_calc_to_load": "The calculated policy alignment data",
            "policy_comparison_period": "The policy comparison periods",
            "votes_with_diff": "All individual votes with alignment scores",
        }

        context["data"] = data

        return context


@app.route("", name="home")
class HomePageView(TitleMixin, TemplateView):
    page_title = ""
    template_name = "votes/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # we want the last three votes for each chamber
        context["chambers"] = Chamber.with_votes()
        # get last commons votes
        context["commons_votes"] = Division.objects.filter(
            chamber__slug=ChamberSlug.COMMONS
        ).order_by("-date", "-division_number")[:5]
        # get the year of the last vote in all chambers
        context["last_dates"] = [
            (x, x.last_decision_date()) for x in context["chambers"]
        ]

        return context


@app.route("people/{filter:slug}", name="people")
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


@app.route("person/{person_id:int}/votes/{year:str}", name="person_votes")
class PersonVotesPageView(TitleMixin, TemplateView):
    page_title = "Person Votes"
    template_name = "votes/person_votes.html"

    def get_context_data(self, person_id: int, year: str, **kwargs):
        context = super().get_context_data(**kwargs)

        person = Person.objects.get(id=person_id)
        context["person"] = person
        if year == "all":
            context["period"] = "All time"
            context["votes"] = Vote.objects.filter(person_id=person_id)
            context["votes_df"] = person.votes_df()
        else:
            try:
                int_year = int(year)
            except (ValueError, TypeError):
                raise ValueError("Year must be a number")
            context["period"] = year
            context["votes"] = Vote.objects.filter(
                person_id=person_id, division__date__year=int_year
            )
            context["votes_df"] = person.votes_df(int_year)
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
    "decisions/division/{chamber_slug:str}/{decision_date:date}/{decision_num:int}",
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
        decision = Division.objects.get(
            chamber__slug=chamber_slug, date=decision_date, division_number=decision_num
        ).apply_analysis_override()

        context["decision"] = decision
        context["relevant_policies"] = [
            x.policy
            for x in PolicyDivisionLink.objects.filter(
                decision=decision
            ).prefetch_related("policy")
        ]
        context["can_add_annotations"] = super_users_or_group(
            self.request.user, PermissionGroupSlug.CAN_ADD_ANNOTATIONS
        )
        context["can_report_whip"] = super_users_or_group(
            self.request.user, PermissionGroupSlug.CAN_REPORT_WHIP
        )
        context["can_add_self_annotations"] = super_users_or_group(
            self.request.user, PermissionGroupSlug.CAN_ADD_SELF_ANNOTATIONS
        )
        context["can_report_self_whip"] = super_users_or_group(
            self.request.user, PermissionGroupSlug.CAN_REPORT_SELF_WHIP
        )

        return context


@app.route(
    "decisions/agreement/{chamber_slug:str}/{decision_date:date}/{decision_ref:str_not_json}",
    name="agreement",
)
class AgreementPageView(TitleMixin, TemplateView):
    page_title = "Agreement"
    template_name = "votes/decision.html"

    def get_context_data(
        self,
        chamber_slug: str,
        decision_date: datetime.date,
        decision_ref: str,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)
        decision = Agreement.objects.get(
            chamber__slug=chamber_slug, date=decision_date, decision_ref=decision_ref
        ).apply_analysis_override()

        context["decision"] = decision
        context["decision"] = decision
        context["relevant_policies"] = [
            x.policy
            for x in PolicyAgreementLink.objects.filter(
                decision=decision
            ).prefetch_related("policy")
        ]
        context["can_add_annotations"] = super_users_or_group(
            self.request.user, PermissionGroupSlug.CAN_ADD_ANNOTATIONS
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
        decisions.sort(key=lambda x: x.date, reverse=True)
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
        context["chambers"] = Chamber.with_votes()
        # get policy statuses
        do_not_display = [PolicyStatus.RETIRED, PolicyStatus.REJECTED]
        if not can_view_draft_content(self.request.user):
            do_not_display.append(PolicyStatus.DRAFT)
        context["statuses"] = [x for x in PolicyStatus if x not in do_not_display]
        return context


@app.route("policies/reports", name="policies_reports")
class PoliciesReportsPageView(TitleMixin, TemplateView):
    page_title = "Policies Reports"
    template_name = "votes/policy_reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        reports = PolicyReport.fetch_multiple(
            statuses=[PolicyStatus.ACTIVE, PolicyStatus.CANDIDATE]
        )

        context["policy_reports"] = reports
        context["policy_level_errors"] = sum([len(x.policy_issues) for x in reports])
        context["policy_level_warnings"] = sum(
            [len(x.policy_warnings) for x in reports]
        )
        context["division_level_errors"] = sum(
            [x.len_division_issues() for x in reports]
        )
        return context


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
    template_name = "votes/policy_report.html"

    def get_context_data(self, policy_id: int, **kwargs):
        context = super().get_context_data(**kwargs)
        context["policy"] = Policy.objects.get(id=policy_id)
        context["policy_report"] = PolicyReport.from_policy(context["policy"])
        return context


@app.route(
    "policies/{chamber_slug:slug}/{status_slug:slug}/{group_slug:slug}",
    name="policy_collection",
)
class PolicyCollectionPageView(TitleMixin, TemplateView):
    page_title = "Policy Collection"
    template_name = "votes/policy_collection.html"

    def get_context_data(
        self, chamber_slug: str, status_slug: str, group_slug: str, **kwargs
    ):
        context = super().get_context_data(**kwargs)
        context["chamber"] = Chamber.objects.get(slug=chamber_slug)
        context["status"] = PolicyStatus(status_slug)
        if group_slug == "all":
            policies = Policy.objects.filter(
                chamber__slug=chamber_slug, status=status_slug
            ).prefetch_related("groups")
        else:
            policies = Policy.objects.filter(
                chamber__slug=chamber_slug, status=status_slug, groups__slug=group_slug
            ).prefetch_related("groups")
        # get unique of all groups
        groups = set()
        for policy in policies:
            groups.update(policy.groups.all())
        policy_collection: list[ChamberPolicyGroup] = []
        for group in groups:
            group_policies = [
                policy for policy in policies if group in policy.groups.all()
            ]
            policy_collection.append(
                ChamberPolicyGroup(name=group.description, policies=group_policies)
            )

        context["policy_collection"] = policy_collection

        return context


@app.route(
    "person/{person_id:int}/policies/{chamber_slug:slug}/{party_slug:slug}/{period_slug:slug}",
    name="person_policy",
)
class PersonPoliciesView(TitleMixin, TemplateView):
    page_title = "Person Policies"
    template_name = "votes/person_policies.html"

    def get_context_data(
        self,
        person_id: int,
        chamber_slug: str,
        party_slug: str,
        period_slug: str,
        **kwargs,
    ):
        # When called from the API view, the request object is not available
        if hasattr(self, "request"):
            rq = self.request
        else:
            rq = None

        context = super().get_context_data(**kwargs)
        person = Person.objects.get(id=person_id)
        chamber = Chamber.objects.get(slug=chamber_slug)
        party = Organization.objects.get(slug=party_slug)
        period = PolicyComparisonPeriod.objects.get(slug=period_slug.upper())

        if rq and can_view_draft_content(rq.user):
            valid_status = [PolicyStatus.ACTIVE, PolicyStatus.CANDIDATE]
        else:
            valid_status = [PolicyStatus.ACTIVE]

        distributions = list(
            person.vote_distributions.filter(
                chamber=chamber,
                period=period,
                party=party,
                policy__status__in=valid_status,
            ).prefetch_related("policy")
        )

        collection = PolicyCollection.from_distributions(
            distributions, url_base=[person_id, chamber_slug, party_slug, period_slug]
        )

        context["person"] = person
        context["chamber"] = chamber
        context["period"] = period
        context["party"] = party
        context["collection"] = collection

        return context


@app.route(
    "person/{person_id:int}/policies/{chamber_slug:slug}/{party_slug:slug}/{period_slug:slug}/{policy_id:int}",
    name="person_policy_solo",
)
class PersonPolicyView(TitleMixin, TemplateView):
    page_title = "Person Policy"
    template_name = "votes/person_policy.html"

    def dfs_from_division_links(
        self,
        votes: list[Vote],
        agreements: list[Agreement],
        division_links: list[PolicyDivisionLink],
        agreement_links: list[PolicyAgreementLink],
    ) -> dict[str, pd.DataFrame]:
        """
        Create 4(or more?) dataframes of the different groupings of votes
        """

        division_vote_lookup = {v.division_id: v for v in votes}
        df_lookup: dict[str, pd.DataFrame] = {}
        division_items = []

        def is_aligned(vote: Vote, link: PolicyDivisionLink) -> str:
            if (
                vote.effective_vote == VotePosition.AYE
                and link.alignment == PolicyDirection.AGREE
            ):
                return "aligned"
            if (
                vote.effective_vote == VotePosition.NO
                and link.alignment == PolicyDirection.AGAINST
            ):
                return "aligned"
            if vote.effective_vote == VotePosition.ABSENT:
                return "na"
            return "not aligned"

        for link in division_links:
            vote = division_vote_lookup.get(link.decision_id)
            if not vote:
                raise ValueError(f"Vote for division {link.decision_id} not found")
            division_items.append(
                {
                    "motion": UrlColumn(
                        url=link.decision.url(), text=link.decision.division_name
                    ),
                    "date": link.decision.date,
                    "person_vote": vote.vote_desc().lower(),
                    "policy_direction": link.alignment,
                    "policy_aligned": is_aligned(vote, link),
                    "policy_strength": f"{link.strength.lower()}_votes",
                }
            )

        if division_items:
            df_lookup.update(
                {
                    str(group): ddf.drop(columns=["policy_strength"])
                    for group, ddf in pd.DataFrame(division_items).groupby(
                        "policy_strength"
                    )
                }
            )

        # now we add agreements
        agreement_items = []

        for link in agreement_links:
            if link.decision not in agreements:
                continue
            agreement = link.decision
            if not link.decision.negative:
                status = StrVotePosition.AYE
            else:
                status = StrVotePosition.NO

            if (
                status == StrVotePosition.AYE
                and link.alignment == PolicyDirection.AGREE
            ):
                alignment = "aligned"
            elif (
                status == StrVotePosition.NO
                and link.alignment == PolicyDirection.AGAINST
            ):
                alignment = "aligned"
            else:
                alignment = "not aligned"

            agreement_items.append(
                {
                    "motion": UrlColumn(
                        url=agreement.url(), text=agreement.decision_name
                    ),
                    "date": agreement.date,
                    "collective_status": status,
                    "policy_direction": link.alignment,
                    "policy_aligned": alignment,
                    "policy_strength": f"{link.strength.lower()}_agreements",
                }
            )

        if agreement_items:
            df_lookup.update(
                {
                    str(group): ddf.drop(columns=["policy_strength"])
                    for group, ddf in pd.DataFrame(agreement_items).groupby(
                        "policy_strength"
                    )
                }
            )

        group_order = {
            "strong_votes": 1,
            "strong_agreements": 2,
            "weak_votes": 3,
            "weak_agreements": 4,
        }

        # resort df_lookup based on key
        df_lookup = dict(sorted(df_lookup.items(), key=lambda x: group_order[x[0]]))

        return df_lookup

    def get_context_data(
        self,
        person_id: int,
        chamber_slug: str,
        party_slug: str,
        period_slug: str,
        policy_id: int,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)
        person = Person.objects.get(id=person_id)
        chamber = Chamber.objects.get(slug=chamber_slug)
        party = Organization.objects.get(slug=party_slug)
        period = PolicyComparisonPeriod.objects.get(slug=period_slug.upper())
        policy = Policy.objects.get(id=policy_id)
        own_distribution = person.vote_distributions.get(
            chamber=chamber, period=period, party=party, policy=policy, is_target=1
        )
        other_distribution = person.vote_distributions.get(
            chamber=chamber, period=period, party=party, policy=policy, is_target=0
        )

        votes = list(
            Vote.objects.filter(
                person=person,
                division__chamber=chamber,
                division__division_links__policy=policy,
            ).prefetch_related("division")
        )

        division_links = list(
            policy.division_links.filter(
                decision__chamber=chamber,
                decision__date__gte=period.start_date,
                decision__date__lte=period.end_date,
            ).prefetch_related("decision")
        )
        agreement_links = list(
            policy.agreement_links.filter(
                decision__chamber=chamber,
                decision__date__gte=period.start_date,
                decision__date__lte=period.end_date,
            ).prefetch_related("decision")
        )

        relevant_memberships = list(
            Membership.objects.filter(chamber=chamber, person=person)
        )

        def is_in_range_agreement(agreement: Agreement) -> bool:
            for membership in relevant_memberships:
                if membership.start_date <= agreement.date <= membership.end_date:
                    return True
            return False

        agreements = [
            x.decision for x in agreement_links if is_in_range_agreement(x.decision)
        ]

        decision_links_and_votes = self.dfs_from_division_links(
            votes=votes,
            agreements=agreements,
            division_links=division_links,
            agreement_links=agreement_links,
        )

        context["person"] = person
        context["chamber"] = chamber
        context["period"] = period
        context["party"] = party
        context["policy"] = policy
        context["own_distribution"] = own_distribution
        context["other_distribution"] = other_distribution
        context["decision_links_and_votes"] = decision_links_and_votes

        return context
