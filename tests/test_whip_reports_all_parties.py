from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

import pytest

from votes.consts import (
    EvidenceType,
    PermissionGroupSlug,
    VotePosition,
    WhipDirection,
    WhipPriority,
)
from votes.models import Division, Organization, Vote, WhipReport

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_user_with_whip_permission():
    # Create a user with whip report permission
    user = User.objects.create_user(
        username="testuser", email="test@example.com", password="testpassword"
    )

    # Create the permission group if it doesn't exist
    group, _ = Group.objects.get_or_create(name=PermissionGroupSlug.CAN_REPORT_WHIP)
    user.groups.add(group)

    return user


def test_apply_to_all_voting_parties(client: Client, test_user_with_whip_permission):
    # Log in the user
    client.login(username="testuser", password="testpassword")

    # Get an existing division from the database
    division = Division.objects.filter(votes__isnull=False).distinct().first()
    assert division is not None, "No division with votes found in database"

    # Ensure there are multiple parties voting in this division
    voting_parties_ids = (
        Vote.objects.filter(division_id=division.id)
        .exclude(vote=VotePosition.ABSENT)
        .values_list("person__memberships__party_id", flat=True)
        .distinct()
    )
    voting_parties_count = Organization.objects.filter(
        id__in=voting_parties_ids
    ).count()
    assert (
        voting_parties_count >= 2
    ), f"Expected at least 2 voting parties, found {voting_parties_count}"

    # Delete any existing whip reports for this division to start clean
    WhipReport.objects.filter(division_id=division.id).delete()

    # Submit form with "apply_to_all_parties" checked
    form_url = reverse(
        "forms", kwargs={"form_slug": "whip", "decision_id": division.id}
    )
    form_data = {
        "apply_to_all_parties": True,
        "whip_direction": WhipDirection.FREE.value,
        "whip_priority": WhipPriority.FREE.value,
        "evidence_type": EvidenceType.OTHER.value,
        "evidence_detail": "Test detail",
    }

    response = client.post(form_url, form_data)

    # Check that the response redirected to the division page
    assert response.status_code == 302

    # Verify that WhipReport objects were created for each voting party (excluding absent)
    whip_reports = WhipReport.objects.filter(division_id=division.id)

    # Should have the same number of whip reports as voting parties
    assert whip_reports.count() == voting_parties_count

    # Verify the whip reports have the correct values
    for report in whip_reports:
        assert report.whip_direction == WhipDirection.FREE
        assert report.whip_priority == WhipPriority.FREE
        assert report.evidence_type == EvidenceType.OTHER
        assert report.evidence_detail == "Test detail"


def test_apply_to_single_party(client: Client, test_user_with_whip_permission):
    # Log in the user
    client.login(username="testuser", password="testpassword")

    # Get an existing division from the database
    division = Division.objects.filter(votes__isnull=False).distinct().first()
    assert division is not None, "No division with votes found in database"

    # Get a party that voted in this division
    voting_party = Organization.objects.filter(
        id__in=Vote.objects.filter(division_id=division.id)
        .exclude(vote=VotePosition.ABSENT)
        .values_list("person__memberships__party_id", flat=True)
    ).first()
    assert voting_party is not None, "No voting party found for this division"

    # Delete any existing whip reports for this division to start clean
    WhipReport.objects.filter(division_id=division.id).delete()

    # Submit form with a single party selected
    form_url = reverse(
        "forms", kwargs={"form_slug": "whip", "decision_id": division.id}
    )
    form_data = {
        "party": voting_party.id,
        "whip_direction": WhipDirection.AGAINST.value,
        "whip_priority": WhipPriority.THREE_LINE.value,
        "evidence_type": EvidenceType.OTHER.value,
        "evidence_detail": "Test single party",
    }

    response = client.post(form_url, form_data)

    # Check that the response redirected to the division page
    assert response.status_code == 302

    # Verify that only one WhipReport object was created
    whip_reports = WhipReport.objects.filter(division_id=division.id)
    assert whip_reports.count() == 1

    # Verify the whip report has the correct values
    report = whip_reports.first()
    assert report is not None
    assert report.party.id == voting_party.id
    assert report.whip_direction == WhipDirection.AGAINST
    assert report.whip_priority == WhipPriority.THREE_LINE
    assert report.evidence_type == EvidenceType.OTHER
    assert report.evidence_detail == "Test single party"
