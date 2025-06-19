from enum import StrEnum
from typing import Type

from django import forms
from django.http import Http404, HttpRequest

from .consts import EvidenceType, VotePosition, WhipDirection, WhipPriority
from .models import (
    AgreementAnnotation,
    Division,
    DivisionAnnotation,
    Membership,
    Organization,
    UserPersonLink,
    Vote,
    VoteAnnotation,
    WhipReport,
)


def enum_to_choices(en: Type[StrEnum]) -> list[tuple[str, str]]:
    return [(enum_.value, enum_.value.title().replace("_", " ")) for enum_ in en]


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
