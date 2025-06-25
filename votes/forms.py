import datetime
from enum import StrEnum
from typing import Type

from django import forms
from django.http import Http404, HttpRequest
from django.utils.text import slugify

from .consts import (
    EvidenceType,
    StatementType,
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
    Signature,
    Statement,
    UserPersonLink,
    VoteAnnotation,
    WhipReport,
)
from .name_reconciliation import person_id_from_name


def enum_to_choices(en: Type[StrEnum]) -> list[tuple[str, str]]:
    return [(enum_.value, enum_.value.title().replace("_", " ")) for enum_ in en]


def validate_signatories_text(
    signatories_text: str, chamber_slug: str, date: datetime.date
) -> list[str]:
    """
    Validate signatories text and return list of names if all are valid.
    """
    if not signatories_text.strip():
        raise forms.ValidationError("At least one signatory is required.")

    lines = [line.strip() for line in signatories_text.split("\n") if line.strip()]
    signatory_errors = []

    for line_num, name in enumerate(lines, 1):
        person_id = person_id_from_name(name, chamber_slug=chamber_slug, date=date)
        if person_id is None:
            signatory_errors.append(f"Line {line_num}: Could not find person '{name}'")

    if signatory_errors:
        raise forms.ValidationError(signatory_errors)

    return lines


def create_signatures_for_statement(
    statement: Statement,
    signatories: list[str],
    date: datetime.date,
    start_order: int = 0,
) -> list[Signature]:
    """
    Create Signature objects for a given statement based on the provided signatories.
    """
    signatures = []
    chamber_slug = statement.chamber.popolo_slug_alias()

    statement_id = statement.id
    if not statement_id:
        raise ValueError("Statement must be saved before creating signatures.")

    for order, name in enumerate(signatories, start=start_order):
        person_id = person_id_from_name(name, chamber_slug=chamber_slug, date=date)
        if person_id:  # This should always be true due to validation
            signature = Signature(
                key=f"{statement.key}-{person_id}",
                statement_id=statement_id,
                person_id=person_id,
                date=date,
                order=order,
                extra_info={},
            )
            signature.save()
            signatures.append(signature)

    return signatures


class DecisionIdMixin:
    @classmethod
    def from_decision_id(cls, decision_id: int):
        return cls()


class WhipForm(forms.Form, DecisionIdMixin):
    title = "Whip Reporting Form"
    desc = "This form is for recording the whip, or party instructions for a division."
    party = forms.ModelChoiceField(
        queryset=Organization.objects.filter(classification="party"),
        label="Select a Party",
        empty_label="Choose a Party",
        widget=forms.Select(attrs={"class": "form-control"}),
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

    def save(self, request: HttpRequest, decision_id: int):
        model = WhipReport(
            division_id=decision_id,
            party_id=self.cleaned_data["party"].id,
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
    signatories = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        label="Signatories (one name per line)",
    )

    def clean_signatories(self):
        """Validate that all signatories can be found and return person IDs"""
        signatories_text = self.cleaned_data.get("signatories", "")

        # Check if chamber and date are available in cleaned_data
        chamber = self.cleaned_data.get("chamber")
        date = self.cleaned_data.get("date")

        if not chamber or not date:
            # If chamber or date is invalid, we can't validate signatories
            # Return the lines for now and let other field validation handle the errors
            if signatories_text.strip():
                return [
                    line.strip()
                    for line in signatories_text.split("\n")
                    if line.strip()
                ]
            return []

        return validate_signatories_text(
            signatories_text, chamber.popolo_slug_alias(), date
        )

    def save(self, request: HttpRequest, decision_id: int | None = None) -> Statement:
        """Save the statement and its signatures"""
        # Create the statement
        chamber: Chamber = self.cleaned_data["chamber"]
        date: datetime.date = self.cleaned_data["date"]
        title: str = self.cleaned_data["statement_title"]

        if not chamber.id:
            raise ValueError("Chamber must be selected and have a valid ID")

        # Generate a unique key and slug
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
            extra_info={},
        )
        statement.save()

        # Verify the statement was saved and has an ID
        if not statement.id:
            raise ValueError("Failed to save statement - no ID generated")

        # Create signatures for each signatory
        signatories = self.cleaned_data["signatories"]
        create_signatures_for_statement(statement, signatories, date)

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
    signatories = forms.CharField(
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
        signatories_text = self.cleaned_data.get("signatories", "")
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
        validated_names = validate_signatories_text(
            signatories_text, chamber_slug, date
        )

        # Check for duplicate signatories (people who already signed this statement)
        existing_signatures = Signature.objects.filter(statement=self.statement)
        existing_person_ids = set()

        for signature in existing_signatures:
            existing_person_ids.add(signature.person_id)

        duplicate_errors = []
        for line_num, name in enumerate(validated_names, 1):
            person_id = person_id_from_name(name, chamber_slug=chamber_slug, date=date)
            if person_id and person_id in existing_person_ids:
                duplicate_errors.append(
                    f"Line {line_num}: '{name}' has already signed this statement"
                )

        if duplicate_errors:
            raise forms.ValidationError(duplicate_errors)

        return validated_names

    def save(self, request: HttpRequest, statement_id: int) -> Statement:
        """Add new signatories to the existing statement"""
        statement = Statement.objects.get(id=statement_id)
        signatories = self.cleaned_data["signatories"]
        date = self.cleaned_data["date"]

        # Get the current maximum order to continue numbering
        existing_signatures = Signature.objects.filter(statement=statement)
        max_order = 0
        if existing_signatures.exists():
            max_order = max(sig.order for sig in existing_signatures)

        # Create new signatures starting after the existing ones
        create_signatures_for_statement(
            statement, signatories, date, start_order=max_order + 1
        )

        return statement
