from __future__ import annotations

import datetime
import json
import re
from enum import StrEnum
from typing import Type

from django import forms
from django.http import Http404, HttpRequest
from django.utils.text import slugify

from pydantic import BaseModel, Field, RootModel, ValidationError, model_validator

from .consts import (
    EvidenceType,
    StatementType,
    VotePosition,
    WhipDirection,
    WhipPriority,
)
from .models import (
    AgreementAnnotation,
    Chamber,
    Division,
    DivisionAnnotation,
    Membership,
    Organization,
    Person,
    Signature,
    Statement,
    Update,
    UserPersonLink,
    Vote,
    VoteAnnotation,
    WhipReport,
)
from .name_reconciliation import person_id_from_name

NON_PARL_PERSON = -1


def enum_to_choices(en: Type[StrEnum]) -> list[tuple[str, str]]:
    return [(enum_.value, enum_.value.title().replace("_", " ")) for enum_ in en]


class MiniSignature(BaseModel):
    name: str
    person_id: int | None = None
    extra_info: dict = Field(default_factory=dict)

    def to_text(self) -> str:
        """
        Convert MiniSignature back to text format.
        If person_id is present, append (person_id) to name.
        If extra_info is present, append (JSON) to name.
        """
        if self.extra_info:
            meta = json.dumps(self.extra_info)
            return f"{self.name} ({meta})"
        elif self.person_id is not None:
            return f"{self.name} ({self.person_id})"
        else:
            return self.name

    @classmethod
    def from_text(cls, name: str) -> MiniSignature:
        """
        Extract person_id and extra metadata from a signatory name.
        - Short format: (10001) at end of name
        - JSON format: ({...}) at end of name
        Returns (person_id, extra_info) tuple. If no match, returns (None, {}).
        """

        person_id = None
        extra_info = {}
        # Short format: (10001) at end

        short_id_match = re.search(r"\((\d+)\)$", name.strip())
        if short_id_match:
            name = re.sub(r"\(\d+\)$", "", name).strip()
            person_id = int(short_id_match.group(1))
            return cls(name=name, person_id=person_id, extra_info=extra_info)
        # JSON format: ({...}) at end
        json_match = re.search(r"\((\{.*\})\)$", name.strip())
        if json_match:
            name = re.sub(r"\(\{.*\}\)$", "", name).strip()
            meta = json.loads(json_match.group(1))
            if isinstance(meta, dict):
                if "person_id" in meta:
                    person_id = meta["person_id"]
                for k, v in meta.items():
                    if k != "person_id":
                        extra_info[k] = v
            else:
                raise ValueError("Invalid JSON metadata format")
        return cls(name=name, person_id=person_id, extra_info=extra_info)


class MiniSignatureList(RootModel):
    """
    Helper function to manage a list of MiniSignature objects
    """

    root: list[MiniSignature]

    def to_text(self) -> str:
        """
        Convert the list of MiniSignature objects back to text format.
        """
        return "\n".join(mini_sig.to_text() for mini_sig in self.root)

    @classmethod
    def from_text(cls, text: str) -> MiniSignatureList:
        """
        Parse signatories text into a list of MiniSignature objects.
        Each line is treated as a separate signatory.
        """
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        mini_sigs = [MiniSignature.from_text(line) for line in lines]
        return cls(root=mini_sigs)

    def __iter__(self):
        return iter(self.root)

    def __len__(self):
        return len(self.root)

    def assign_person_ids_from_chamber(
        self,
        chamber_slug: str,
        date: datetime.date,
        allow_signatures_without_person_ids: bool = False,
    ):
        for mini_sig in self:
            if mini_sig.person_id is None:
                mini_sig.person_id = person_id_from_name(
                    mini_sig.name, chamber_slug=chamber_slug, date=date
                )
            if mini_sig.person_id is None and allow_signatures_without_person_ids:
                mini_sig.person_id = NON_PARL_PERSON

    def validate_signatories_text(
        self,
        chamber_slug: str,
        date: datetime.date,
        allow_signatures_without_person_ids: bool = False,
    ) -> MiniSignatureList:
        """
        Validate signatories text and return list of names if all are valid.
        """
        if not self.root:
            raise forms.ValidationError("At least one signatory is required.")

        self.assign_person_ids_from_chamber(
            chamber_slug=chamber_slug,
            date=date,
            allow_signatures_without_person_ids=allow_signatures_without_person_ids,
        )

        signatory_errors = []
        previous_person_ids = []
        for line_num, mini_sig in enumerate(self, 1):
            if mini_sig.person_id is None:
                signatory_errors.append(
                    f"Line {line_num}: Could not find person '{mini_sig.name}'"
                )
            else:
                if (
                    mini_sig.person_id in previous_person_ids
                    and mini_sig.person_id != NON_PARL_PERSON
                ):
                    signatory_errors.append(
                        f"Line {line_num}: Duplicate signatory '{mini_sig.name}' found"
                    )
            previous_person_ids.append(mini_sig.person_id)

        if signatory_errors:
            raise forms.ValidationError(signatory_errors)

        return self

    def create_signatures_for_statement(
        self,
        statement: Statement,
        date: datetime.date,
        start_order: int = 0,
        allow_signatures_without_person_ids: bool = False,
    ) -> list[Signature]:
        """
        Create Signature objects for a given statement based on the provided signatories.

        Extra properties can be included in the signatory name using JSON syntax, e.g.:
            John Smith [{"person_id": 1234, "role": "sponsor"}]
            Jane Doe [{"person_id": 5678, "role": "opponent"}].

        """
        signatures = []
        if statement.chamber.slug == "other":
            chamber_slug = "house-of-commons"
        else:
            chamber_slug = statement.chamber.popolo_slug_alias()

        statement_id = statement.id
        if not statement_id:
            raise ValueError("Statement must be saved before creating signatures.")

        self.assign_person_ids_from_chamber(
            chamber_slug=chamber_slug,
            date=date,
            allow_signatures_without_person_ids=allow_signatures_without_person_ids,
        )

        for order, mini_sig in enumerate(self, start=start_order):
            if mini_sig.person_id == NON_PARL_PERSON:
                # Strip metadata from name before saving
                mini_sig.extra_info["name"] = mini_sig.name
                key = f"{statement.key}-noperson-{slugify(mini_sig.name)}-{order}"
                person_id_val = None
            elif mini_sig.person_id:
                key = f"{statement.key}-{mini_sig.person_id}"
                person_id_val = mini_sig.person_id
            else:
                raise ValueError(
                    f"Cannot create signature for '{mini_sig.name}' without a valid person ID (or -1)."
                )
            signature = Signature(
                key=key,
                statement_id=statement_id,
                person_id=person_id_val,
                date=date,
                order=order,
                extra_info=mini_sig.extra_info,
            )
            signature.save()
            signatures.append(signature)

        return signatures


class MiniSigField(forms.CharField):
    def to_python(self, value: str) -> MiniSignatureList:
        if not value:
            return MiniSignatureList(root=[])
        try:
            mini_sig_list = MiniSignatureList.from_text(value)
            return mini_sig_list
        except ValueError as e:
            raise forms.ValidationError(f"Error parsing signatories: {e}")

    def prepare_value(self, value: MiniSignatureList | str) -> str:
        if isinstance(value, MiniSignatureList):
            return value.to_text()
        return value or ""


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

        Update.create_task(
            instructions={
                "model": "export_annotations",
            },
            created_via="bulk_vote_annotation_form",
            check_for_running=True,
        )


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

        Update.create_task(
            instructions={
                "model": "export_annotations",
            },
            created_via="bulk_vote_annotation_form",
            check_for_running=True,
        )


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

        # Queue an update to export annotations after any changes
        if created_count > 0 or updated_count > 0 or deleted_count > 0:
            Update.create_task(
                instructions={
                    "model": "export_annotations",
                },
                created_via="bulk_vote_annotation_form",
                check_for_running=True,
            )
        return result_message


class StatementForm(forms.Form):
    title = "Add Statement Form"
    desc = "This form is for adding new statements with signatories."

    statement_title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Title",
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Date",
    )

    chamber = forms.ModelChoiceField(
        queryset=Chamber.objects.all(),
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Chamber",
    )
    statement_type = forms.ChoiceField(
        choices=enum_to_choices(StatementType),
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Statement Type",
    )
    url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={"class": "form-control"}),
        label="Source URL",
    )
    content = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
        label="Statement Content",
    )
    signatories = MiniSigField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        label="Signatories (one name per line)",
    )
    allow_signatures_without_person_ids = forms.BooleanField(
        required=False,
        label="Allow signatures without person IDs",
        help_text="If ticked, names that can't be matched will be saved as signatures without a person.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_date(self):
        """Ensure the date is not more than a month after the current date."""
        date = self.cleaned_data["date"]
        if not isinstance(date, datetime.date):
            raise forms.ValidationError("Invalid date format.")
        if date > datetime.date.today() + datetime.timedelta(days=30):
            raise forms.ValidationError("Date cannot be more than a month after today.")
        return date

    def clean_signatories(self):
        """Validate that all signatories can be found and return person IDs"""
        signatories = self.cleaned_data.get("signatories", MiniSignatureList(root=[]))
        allow_signatures_without_person_ids = self.data.get(
            "allow_signatures_without_person_ids", False
        )

        chamber: Chamber | None = self.cleaned_data.get("chamber")
        date = self.cleaned_data.get("date")

        if not chamber or not date:
            self.add_error("chamber", "Chamber is required.")
            self.add_error("date", "Date is required.")
            return signatories

        if chamber.slug == "other":
            chamber_alias = "house-of-commons"
        else:
            chamber_alias = chamber.popolo_slug_alias()

        return signatories.validate_signatories_text(
            chamber_alias,
            date,
            allow_signatures_without_person_ids=allow_signatures_without_person_ids,
        )

    def save(self, request: HttpRequest, decision_id: int | None = None) -> Statement:
        """Save the statement, its signatures, and party breakdowns"""
        chamber: Chamber = self.cleaned_data["chamber"]
        date: datetime.date = self.cleaned_data["date"]
        title: str = self.cleaned_data["statement_title"]

        if not chamber.id:
            raise ValueError("Chamber must be selected and have a valid ID")

        key = f"stmt-{chamber.slug}-{date.isoformat()}-{slugify(title)}"
        slug = slugify(title)
        slug = Statement.get_free_slug(slug, date=date)

        statement = Statement(
            key=key,
            chamber_slug=chamber.slug,
            chamber_id=chamber.id,
            title=title,
            slug=slug,
            statement_text=self.cleaned_data["content"],
            original_id=None,
            date=date,
            type=StatementType(self.cleaned_data["statement_type"]),
            url=self.cleaned_data.get("url", ""),
            extra_info={
                "data_entered_via": "form",
                "data_entered_by": request.user.username,
            },
        )
        statement.save()

        if not statement.id:
            raise ValueError("Failed to save statement - no ID generated")

        # Create signatures for each signatory
        signatories: MiniSignatureList = self.cleaned_data["signatories"]
        allow_no_person = self.cleaned_data.get(
            "allow_signatures_without_person_ids", False
        )

        signatories.create_signatures_for_statement(
            statement,
            date,
            allow_signatures_without_person_ids=allow_no_person,
        )

        # Generate party breakdowns for the statement
        statement.generate_party_breakdowns()

        # Create export update task to update parquet files
        Update.create_task(
            {"model": "statement_export"},
            created_via="StatementForm",
            check_for_running=True,
        )

        return statement


class AddSignatoriesForm(forms.Form):
    title = "Add Signatories to Statement"
    desc = "This form is for adding new signatories to an existing statement."

    statement_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        label="Statement ID",
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Signature Date",
        help_text="Date when the signatories signed (may be different from statement date)",
    )
    signatories = MiniSigField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        label="New Signatories (one name per line)",
        help_text="Enter one signatory name per line. Names will be validated against the chamber membership.",
        required=False,  # We'll handle validation in clean_signatories
    )

    def __init__(self, *args, statement: Statement | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.statement = statement
        if statement:
            self.initial["statement_id"] = statement.id

    @classmethod
    def from_statement_id(cls, statement_id: int) -> "AddSignatoriesForm":
        """Create form from a statement ID"""
        statement = Statement.objects.get(id=statement_id)
        return cls(statement=statement)

    def clean_date(self):
        """Ensure the date is not more than a month after the current date."""
        date = self.cleaned_data["date"]
        if not isinstance(date, datetime.date):
            raise forms.ValidationError("Invalid date format.")
        if date > datetime.date.today() + datetime.timedelta(days=30):
            raise forms.ValidationError("Date cannot be more than a month after today.")
        return date

    def clean_statement_id(self):
        """Validate that the statement exists"""
        statement_id = self.cleaned_data["statement_id"]
        try:
            statement = Statement.objects.get(id=statement_id)
            self.statement = statement
            return statement_id
        except Statement.DoesNotExist:
            raise forms.ValidationError("Statement not found.")

    def clean_signatories(self):
        """Validate that all signatories can be found and return person IDs"""
        signatories: MiniSignatureList = self.cleaned_data.get(
            "signatories", MiniSignatureList(root=[])
        )
        date = self.cleaned_data.get("date")

        if not self.statement:
            # Try to get statement from statement_id if not set
            statement_id = self.cleaned_data.get("statement_id")
            if statement_id:
                try:
                    self.statement = Statement.objects.get(id=statement_id)
                except Statement.DoesNotExist:
                    raise forms.ValidationError(
                        "Cannot validate signatories without valid statement."
                    )
            else:
                raise forms.ValidationError(
                    "Cannot validate signatories without statement information."
                )

        if not date:
            raise forms.ValidationError(
                "Cannot validate signatories without signature date."
            )

        chamber_slug = self.statement.chamber.popolo_slug_alias()
        validated_names = signatories.validate_signatories_text(chamber_slug, date)

        # Check for duplicate signatories (people who already signed this statement)
        existing_signatures = Signature.objects.filter(statement=self.statement)
        existing_person_ids = set()

        for signature in existing_signatures:
            existing_person_ids.add(signature.person_id)

        duplicate_errors = []
        for line_num, mini_sig in enumerate(validated_names, 1):
            if mini_sig.person_id and mini_sig.person_id in existing_person_ids:
                duplicate_errors.append(
                    f"Line {line_num}: '{mini_sig.name}' has already signed this statement"
                )

        if duplicate_errors:
            raise forms.ValidationError(duplicate_errors)

        return validated_names

    def save(self, request: HttpRequest, statement_id: int) -> Statement:
        """Add new signatories to the existing statement"""
        statement = Statement.objects.get(id=statement_id)
        signatories: MiniSignatureList = self.cleaned_data["signatories"]
        date = self.cleaned_data["date"]

        # Get the current maximum order to continue numbering
        existing_signatures = Signature.objects.filter(statement=statement)
        max_order = 0
        if existing_signatures.exists():
            max_order = max(sig.order for sig in existing_signatures)

        # Create new signatures starting after the existing ones

        signatories.create_signatures_for_statement(
            statement=statement,
            date=date,
            start_order=max_order + 1,
            allow_signatures_without_person_ids=False,
        )

        # Regenerate party breakdowns for the updated statement
        statement.generate_party_breakdowns()

        # Create export update task to update parquet files
        Update.create_task(
            {"model": "statement_export"},
            created_via="AddSignatoriesForm",
            check_for_running=True,
        )

        return statement
