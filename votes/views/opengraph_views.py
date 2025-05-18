from __future__ import annotations

import datetime
import re
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.generic import View

from PIL import Image

from ..models import (
    Agreement,
    Chamber,
    DecisionTag,
    Division,
    Membership,
    Person,
    Policy,
)
from .opengraph import draw_custom_image, draw_vote_image


class BaseOpenGraphView(View):
    """Base view for OpenGraph images."""

    def get_image(self, request, *args, **kwargs) -> Image.Image:
        """Method to be implemented by child classes to provide an image."""
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        """Handle GET request by returning the image with proper MIME type."""
        # Get the image from the child class
        image = self.get_image(request, *args, **kwargs)

        # Save image to a BytesIO object
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        # Create response with the image data
        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        return response


class DivisionOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for divisions."""

    def get_image(self, request, division_id: int, **kwargs) -> Image.Image:
        try:
            division = Division.objects.get(id=division_id)
            return draw_vote_image(division)
        except Division.DoesNotExist:
            raise Http404("Division not found")


class AgreementOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for agreements."""

    def get_image(self, request, agreement_id: int, **kwargs) -> Image.Image:
        try:
            agreement = Agreement.objects.get(id=agreement_id)
            header = agreement.safe_decision_name()
            chamber = agreement.chamber.name
            date = agreement.date.strftime("%Y-%m-%d")
            subheader = f"{chamber} - {date}"
            return draw_custom_image(header, subheader, include_logo=True)
        except Agreement.DoesNotExist:
            raise Http404("Agreement not found")


class GeneralOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for various general pages."""

    def get_image(self, request, page_slug: str, **kwargs) -> Image.Image:
        match page_slug:
            case "home":
                return draw_custom_image(
                    "TheyWorkForYou Votes",
                    include_logo=False,
                )
            case "data":
                return draw_custom_image(
                    "Bulk data",
                    include_logo=True,
                )
            case "decisions":
                return draw_custom_image(
                    "Parliamentary Decisions",
                    include_logo=True,
                )
            case "policies":
                return draw_custom_image(
                    "Policy Positions",
                    include_logo=True,
                )
            case "people":
                return draw_custom_image(
                    "Representatives",
                    include_logo=True,
                )
            case "tags":
                return draw_custom_image(
                    "Decision Tags",
                    include_logo=True,
                )
            case _:
                # return 404 if page_slug is not found
                raise Http404("Page not found")


class PersonOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for person pages."""

    def get_image(self, request, person_id: int, **kwargs) -> Image.Image:
        try:
            person = Person.objects.get(id=person_id)
            # Create a custom image with the person's name
            header = person.name

            # Add current role if available - find current memberships
            current_membership = Membership.objects.filter(
                person=person,
                start_date__lte=datetime.date.today(),
                end_date__gte=datetime.date.today(),
            ).first()

            subheader = ""
            if current_membership:
                party_name = current_membership.party.name
                chamber_name = current_membership.chamber.name
                subheader = f"{party_name} - {chamber_name}"

            return draw_custom_image(header, subheader, include_logo=True)
        except Person.DoesNotExist:
            raise Http404("Person not found")


class PolicyOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for policy pages."""

    def get_image(self, request, policy_id: int, **kwargs) -> Image.Image:
        try:
            policy = Policy.objects.get(id=policy_id)
            # Create a custom image with the policy name and chamber
            header = policy.name
            subheader = f"{policy.chamber.name} Policy"

            return draw_custom_image(header, subheader, include_logo=True)
        except Policy.DoesNotExist:
            raise Http404("Policy not found")


class TagOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for tag pages."""

    def get_image(self, request, tag_type: str, tag_slug: str, **kwargs) -> Image.Image:
        try:
            tag = DecisionTag.objects.get(tag_type=tag_type, slug=tag_slug)
            header = f"Tag: {tag.name}"

            # Count associated decisions
            decision_count = tag.divisions.count() + tag.agreements.count()
            subheader = f"{decision_count} Decisions"

            return draw_custom_image(header, subheader, include_logo=True)
        except DecisionTag.DoesNotExist:
            raise Http404("Tag not found")


class MarkdownOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for markdown pages."""

    def get_image(self, request, markdown_slug: str, **kwargs) -> Image.Image:
        # Try to find the markdown file
        markdown_slug = re.sub(r"[^a-zA-Z0-9_-]", "", markdown_slug)
        template_path = Path(
            settings.BASE_DIR, "votes", "markdown/{}.md".format(markdown_slug)
        )

        try:
            markdown_body = template_path.read_text()

            # Extract the H1 header to use as the page title
            lines = markdown_body.splitlines()
            h1_header = lines[0]
            if h1_header.startswith("# "):
                header = h1_header[2:]
            else:
                header = markdown_slug.replace("-", " ").title()

            return draw_custom_image(header, include_logo=True)
        except FileNotFoundError:
            raise Http404("Markdown page not found")


class DecisionsListOpenGraphImageView(BaseOpenGraphView):
    """View for serving OpenGraph images for decisions list pages."""

    def get_image(
        self, request, chamber_slug: str, year: int, month: int | None = None, **kwargs
    ) -> Image.Image:
        try:
            chamber = Chamber.objects.get(slug=chamber_slug)

            if month:
                # Format for monthly view
                date_obj = datetime.date(year, month, 1)
                header = f"{date_obj.strftime('%B %Y')} {chamber.name}"
            else:
                # Format for yearly view
                header = f"{chamber.name} ({year})"

            return draw_custom_image(header, include_logo=True)
        except (Chamber.DoesNotExist, ValueError):
            raise Http404("Chamber or date not found")
