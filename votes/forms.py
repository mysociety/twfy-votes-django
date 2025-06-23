import json
from enum import StrEnum
from typing import Type

from django import forms
from django.http import Http404, HttpRequest

from pydantic import BaseModel, Field, RootModel, ValidationError, model_validator

from .consts import EvidenceType, VotePosition, WhipDirection, WhipPriority
from .models import (
    AgreementAnnotation,
    Division,
    DivisionAnnotation,
    Membership,
    Organization,
    Person,
    UserPersonLink,
    Vote,
    VoteAnnotation,
    WhipReport,
)


def enum_to_choices(en: Type[StrEnum]) -> list[tuple[str, str]]:
    return [(enum_.value, enum_.value.title().replace("_", " ")) for enum_ in en]


class VoteAnnotationUpdate(BaseModel):
    """
    Represents a single vote annotation update for a person
    """

    person_id: int
    link: str = ""  # Optional field, can be empty for delete operations
    detail: str = ""
    delete: bool = Field(
        default=False, description="Set to true to delete this annotation"
    )

    @model_validator(mode="after")
    def check_required_fields(self):
        """
        Ensure that at least one of link or detail is provided unless delete is true
        """
        if self.delete:
            # If delete is true, no other fields are required
            return self

        if not self.link:
            raise ValueError("Either 'link' must be provided unless 'delete' is true")

        return self


class VoteUpdates(RootModel):
    """
    Root model containing a list of vote annotation updates
    """

    root: list[VoteAnnotationUpdate]

    def __iter__(self):
        """
        Allow iteration over the root list directly
        """
        return iter(self.root)


class DecisionIdMixin:
    @classmethod
    def from_decision_id(cls, decision_id: int):
        return cls(initial={"decision_id": decision_id})  # type: ignore


class WhipForm(forms.Form, DecisionIdMixin):
    title = "Whip Reporting Form"
    desc = "This form is for recording the whip, or party instructions for a division."
    party = forms.ModelChoiceField(
        queryset=Organization.objects.filter(classification="party"),
        label="Select a Party",
        empty_label="Choose a Party",
        widget=forms.Select(attrs={"class": "form-control"}),
        required=False,
    )
    apply_to_all_parties = forms.BooleanField(
        required=False,
        label="Apply to all voting parties",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    whip_direction = forms.ChoiceField(
        choices=enum_to_choices(WhipDirection),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    whip_priority = forms.ChoiceField(
        choices=enum_to_choices(WhipPriority),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    evidence_type = forms.ChoiceField(
        choices=enum_to_choices(EvidenceType),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    evidence_detail = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control"}), required=False
    )

    def clean(self):
        cleaned_data = super().clean()
        apply_to_all_parties = cleaned_data.get("apply_to_all_parties")
        party = cleaned_data.get("party")

        if not apply_to_all_parties and not party:
            self.add_error(
                "party", 'Please select a party or check "Apply to all voting parties"'
            )

        return cleaned_data

    def save(self, request: HttpRequest, decision_id: int):
        if self.cleaned_data.get("apply_to_all_parties"):
            # Get all parties that had members voting in this division
            voting_parties_ids = (
                Vote.objects.filter(division_id=decision_id)
                .exclude(vote=VotePosition.ABSENT)
                .select_related("person")
                .values_list("person__memberships__party_id", flat=True)
                .distinct()
            )

            voting_parties = Organization.objects.filter(id__in=voting_parties_ids)
        else:
            voting_parties = [self.cleaned_data["party"]]

        for party in voting_parties:
            model = WhipReport(
                division_id=decision_id,
                party=party,
                whip_direction=self.cleaned_data["whip_direction"],
                whip_priority=self.cleaned_data["whip_priority"],
                evidence_type=self.cleaned_data["evidence_type"],
                evidence_detail=self.cleaned_data["evidence_detail"],
            )
            model.save()


class RepWhipForm(forms.Form, DecisionIdMixin):
    title = "Whip Reporting Form"
    desc = "This form is for representatives to self-report the whip for their party."

    whip_direction = forms.ChoiceField(
        choices=enum_to_choices(WhipDirection),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    whip_strength = forms.ChoiceField(
        choices=enum_to_choices(WhipPriority),
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def save(self, request: HttpRequest, decision_id: int):
        division = Division.objects.get(id=decision_id)
        person_id = request.POST.get("person_id")
        # get membership for date
        membership = Membership.objects.filter(
            person_id=person_id,
            start_date__lte=division.date,
            end_date__gte=division.date,
            chamber=division.chamber,
        ).first()
        current_party = membership.party_id if membership else None
        if not current_party:
            return Http404("No party found for this person on this date")

        model = WhipReport(
            division_id=decision_id,
            whip_direction=self.cleaned_data["whip_direction"],
            party_id=current_party,
            whip_priority=self.cleaned_data["whip_strength"],
            evidence_type=EvidenceType.REP,
        )
        model.save()


class BaseAnnotationForm(forms.Form, DecisionIdMixin):
    detail = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"class": "form-control"})
    )
    link = forms.URLField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control"})
    )


class DivisionAnnotationForm(BaseAnnotationForm):
    title = "Division Annotation Form"
    desc = "This form is for adding annotations (links) to divisions."

    def save(self, request: HttpRequest, decision_id: int):
        model = DivisionAnnotation(
            division_id=decision_id,
            detail=self.cleaned_data["detail"],
            link=self.cleaned_data["link"],
        )
        model.save()


class AgreementAnnotationForm(BaseAnnotationForm):
    title = "Agreement Annotation Form"
    desc = "This form is for adding annotations (links) to agreements."

    def save(self, request: HttpRequest, decision_id: int):
        model = AgreementAnnotation(
            agreement_id=decision_id,
            detail=self.cleaned_data["detail"],
            link=self.cleaned_data["link"],
        )
        model.save()


class OpenRepAnnotationForm(BaseAnnotationForm):
    title = "Vote Annotation Form"
    desc = "This form is for adding annotations to votes for any person."
    person_id = forms.IntegerField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    def save(self, request: HttpRequest, decision_id: int):
        model = VoteAnnotation(
            division_id=decision_id,
            person_id=self.cleaned_data["person_id"],
            detail=self.cleaned_data["detail"],
            link=self.cleaned_data["link"],
        )
        model.save()


class RepAnnotationForm(BaseAnnotationForm):
    title = "Vote Annotation Form"
    desc = "This form is for adding annotations to votes made by the logged-in user."

    def save(self, request: HttpRequest, decision_id: int):
        link = UserPersonLink.objects.get(user=request.user)
        if not link:
            return Http404("No link found for this user")
        model = VoteAnnotation(
            division_id=decision_id,
            person_id=link.person_id,
            detail=self.cleaned_data["detail"],
            link=self.cleaned_data["link"],
        )
        model.save()


class BulkVoteAnnotationForm(forms.Form, DecisionIdMixin):
    """
    Form for handling bulk vote annotation updates
    """

    title = "Bulk Vote Annotation Form"
    desc = "This form is for adding or updating multiple vote annotations at once."

    decision_id = forms.IntegerField(widget=forms.HiddenInput())
    annotations_json = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 15, "cols": 60, "class": "form-control"}),
        label="Vote Annotations (JSON)",
        help_text="""
        Provide a JSON list of vote annotations in the following format:
        [
            {
                "person_id": 1234,
                "link": "https://example.com/reference",
                "detail": "Optional explanation"
            },
            ...
        ]
        
        To delete an existing annotation, include the "delete" flag:
        {
            "person_id": 1234,
            "delete": true
        }
        """,
    )

    def clean_annotations_json(self):
        """
        Validates the JSON data and converts it to a Pydantic model
        """

        json_data = self.cleaned_data.get("annotations_json")
        if not json_data:
            raise forms.ValidationError("This field is required.")

        # Parse the JSON data
        try:
            annotations_data = json.loads(json_data)
        except json.JSONDecodeError as e:
            # Format the JSON error in a user-friendly way
            line_col = (
                f"line {e.lineno}, column {e.colno}"
                if hasattr(e, "lineno")
                else "unknown position"
            )
            error_msg = f"Invalid JSON format at {line_col}: {e.msg}"
            raise forms.ValidationError(error_msg)

        # Validate with Pydantic model
        try:
            vote_updates = VoteUpdates.model_validate(annotations_data)
        except ValidationError as e:
            # Format validation errors in a user-friendly way
            error_messages = []
            for error in e.errors():
                location = ".".join(str(loc) for loc in error["loc"])
                message = error["msg"]
                error_messages.append(f"Error at {location}: {message}")

            formatted_error = (
                "Please fix the following validation errors:\n"
                + "\n".join(error_messages)
            )
            raise forms.ValidationError(formatted_error)

        # Check if all person IDs exist in the database
        person_ids = [update.person_id for update in vote_updates]
        existing_person_ids = set(
            Person.objects.filter(id__in=person_ids).values_list("id", flat=True)
        )
        missing_person_ids = [
            person_id
            for person_id in person_ids
            if person_id not in existing_person_ids
        ]

        if missing_person_ids:
            error_msg = f"The following person IDs do not exist: {', '.join(map(str, missing_person_ids))}"
            raise forms.ValidationError(error_msg)

        # Return the parsed and validated data so it's available in save
        return vote_updates

    def save(self, request: HttpRequest, decision_id: int):
        """
        Process the validated data and create/update/delete annotations
        This method assumes all validation has already happened in clean method
        """

        # Get the validated vote updates from cleaned_data
        vote_updates: VoteUpdates = self.cleaned_data["annotations_json"]

        # Process each annotation update
        created_count = 0
        updated_count = 0
        deleted_count = 0

        for update in vote_updates:
            # Check if this annotation should be deleted
            if update.delete:
                try:
                    annotation = VoteAnnotation.objects.get(
                        division_id=decision_id, person_id=update.person_id
                    )
                    annotation.delete()
                    deleted_count += 1
                except VoteAnnotation.DoesNotExist:
                    # If it doesn't exist, nothing to delete
                    pass
            else:
                # Try to find existing annotation for this person and division
                annotation, created = VoteAnnotation.objects.update_or_create(
                    division_id=decision_id,
                    person_id=update.person_id,
                    defaults={
                        "link": update.link,
                        "detail": update.detail,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        result_message = f"Successfully processed annotations: {created_count} created, {updated_count} updated"
        if deleted_count > 0:
            result_message += f", {deleted_count} deleted"

        return result_message
