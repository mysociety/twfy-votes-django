from django.contrib.auth.models import Group, User
from django.test import Client

import pytest

from votes.consts import EvidenceType, PermissionGroupSlug, WhipDirection, WhipPriority
from votes.models import Division, Organization, UserPersonLink, WhipReport

pytestmark = pytest.mark.django_db


@pytest.fixture
def division_id():
    return Division.objects.get(key="pw-2016-12-13-109-commons").id


@pytest.fixture
def test_rep_user():
    """
    mock up a user for diane abbott to add annotations
    """
    user = User.objects.create_user(username="testuser", password="password")
    link = UserPersonLink.objects.create(user=user, person_id=10001)
    self_annotations = Group.objects.get(
        name=PermissionGroupSlug.CAN_ADD_SELF_ANNOTATIONS
    )
    self_whip = Group.objects.get(name=PermissionGroupSlug.CAN_REPORT_SELF_WHIP)
    user.groups.add(self_annotations)
    user.groups.add(self_whip)
    yield user
    user.delete()
    link.delete()


@pytest.fixture
def test_super_user():
    user = User.objects.create_user(
        username="testuser", password="password", is_superuser=True
    )
    user.is_superuser = True
    yield user
    user.delete()


@pytest.fixture
def test_has_draft_power_user():
    user = User.objects.create_user(username="testuserdraft", password="password")
    group = Group.objects.get(name=PermissionGroupSlug.CAN_VIEW_DRAFT)
    user.groups.add(group)
    yield user
    user.delete()


@pytest.fixture
def test_has_annotation_power_user():
    user = User.objects.create_user(username="testuserdraft", password="password")
    group = Group.objects.get(name=PermissionGroupSlug.CAN_ADD_ANNOTATIONS)
    user.groups.add(group)
    yield user
    user.delete()


@pytest.fixture
def test_report_whip_power_user():
    user = User.objects.create_user(username="testuserdraft", password="password")
    group = Group.objects.get(name=PermissionGroupSlug.CAN_REPORT_WHIP)
    user.groups.add(group)
    yield user
    user.delete()


def test_whip_form_visible(client: Client, division_id: int):
    response = client.get(f"/submit/whip/{division_id}")
    assert response.status_code == 404


def test_whip_form_visible_superuser(
    client: Client, division_id: int, test_super_user: User
):
    client.force_login(test_super_user)
    response = client.get(f"/submit/whip/{division_id}")
    assert response.status_code == 200


def test_whip_form_visible_group(
    client: Client, division_id: int, test_report_whip_power_user: User
):
    client.force_login(test_report_whip_power_user)
    response = client.get(f"/submit/whip/{division_id}")
    assert response.status_code == 200


def test_whip_form_visible_group_incorrect(
    client: Client, division_id: int, test_has_annotation_power_user: User
):
    client.force_login(test_has_annotation_power_user)
    response = client.get(f"/submit/whip/{division_id}")
    assert response.status_code == 404


def test_self_whip_visible(
    client: Client,
    division_id: int,
):
    response = client.get(f"/submit/rep_whip/{division_id}")
    assert response.status_code == 404


def test_self_whip_visible_rep(client: Client, division_id: int, test_rep_user: User):
    client.force_login(test_rep_user)
    response = client.get(f"/submit/rep_whip/{division_id}")
    assert response.status_code == 200


def test_self_annotate_visible(client: Client, division_id: int):
    response = client.get(f"/submit/rep_annotation/{division_id}")

    response = client.get("/submit/rep_annotation/78288")
    assert response.status_code == 404


def test_form_visible(
    client: Client,
    division_id: int,
):
    response = client.get(f"/submit/division_annotation/{division_id}")
    assert response.status_code == 404


def test_form_visible_superuser(
    client: Client, division_id: int, test_super_user: User
):
    client.force_login(test_super_user)
    response = client.get(f"/submit/division_annotation/{division_id}")
    assert response.status_code == 200


def test_form_visible_group_incorrect(
    client: Client, division_id: int, test_report_whip_power_user: User
):
    client.force_login(test_report_whip_power_user)
    response = client.get(f"/submit/division_annotation/{division_id}")
    assert response.status_code == 404


def test_form_visible_group(
    client: Client, division_id: int, test_has_annotation_power_user: User
):
    client.force_login(test_has_annotation_power_user)
    response = client.get(f"/submit/division_annotation/{division_id}")
    assert response.status_code == 200


def test_policies_restricted_not_loggedin(client: Client):
    response = client.get("/policies")
    assert response.status_code == 200
    assert "/policies/commons/draft/all" not in response.content.decode()


def test_visible_form_links(client: Client):
    response = client.get("/decisions/division/commons/2024-12-11/66")
    content = response.content.decode()
    assert "Add your vote annotation" not in content
    assert "Report your whip" not in content
    assert "Add an annotation" not in content
    assert "Report whip info" not in content
    assert "Add a vote annotation" not in content


def test_visible_form_links_rep_user(client: Client, test_rep_user: User):
    client.force_login(test_rep_user)
    response = client.get("/decisions/division/commons/2024-12-11/66")
    content = response.content.decode()
    assert "Add your vote annotation" in content
    assert "Report your whip" in content
    assert "Add an annotation" not in content
    assert "Report whip info" not in content
    assert "Add a vote annotation" not in content


def test_visible_form_links_power_user(
    client: Client, test_has_annotation_power_user: User
):
    client.force_login(test_has_annotation_power_user)
    response = client.get("/decisions/division/commons/2024-12-11/66")
    content = response.content.decode()
    assert "Add an annotation" in content
    assert "Report whip info" not in content
    assert "Add a vote annotation" in content


def test_visible_form_links_super_user(client: Client, test_super_user: User):
    client.force_login(test_super_user)
    response = client.get("/decisions/division/commons/2024-12-11/66")
    content = response.content.decode()
    assert "Add an annotation" in content
    assert "Report whip info" in content
    assert "Add a vote annotation" in content


def test_policies_draft_visible_superuser(client: Client, test_super_user: User):
    client.force_login(test_super_user)
    response = client.get("/policies")
    assert response.status_code == 200
    assert "/policies/commons/draft/all" in response.content.decode()


def test_policies_draft_visible_group(client: Client, test_has_draft_power_user: User):
    client.force_login(test_has_draft_power_user)
    response = client.get("/policies")
    assert response.status_code == 200
    assert "/policies/commons/draft/all" in response.content.decode()


@pytest.fixture
def division_with_whip_report():
    """
    Create a division with a whip report for testing
    """
    division = Division.objects.get(key="pw-2016-12-13-109-commons")

    # Get Labour party organization
    labour_party = Organization.objects.filter(name="Labour").first()

    whip_report = WhipReport.objects.create(
        division=division,
        party=labour_party,
        whip_direction=WhipDirection.FOR,
        whip_priority=WhipPriority.THREE_LINE,
        evidence_type=EvidenceType.REP,
    )
    yield division, whip_report
    # Clean up
    whip_report.delete()


def test_whip_report_edit_link_not_visible(client: Client, division_with_whip_report):
    """
    Test that whip report edit links are not visible for non-superuser
    """
    division, whip_report = division_with_whip_report
    response = client.get(
        f"/decisions/division/commons/{division.date}/{division.division_number}"
    )
    content = response.content.decode()
    # Check that the whip report table is visible but the ID column is not
    assert "Whip direction" in content
    assert "Party" in content
    # The admin link ID column should not be visible
    assert f"/admin/votes/whipreport/{whip_report.id}/change/" not in content


def test_whip_report_edit_link_visible_superuser(
    client: Client, test_super_user: User, division_with_whip_report
):
    """
    Test that whip report edit links are visible for superusers
    """
    division, whip_report = division_with_whip_report
    client.force_login(test_super_user)
    response = client.get(
        f"/decisions/division/commons/{division.date}/{division.division_number}"
    )
    content = response.content.decode()
    # Check that the whip report table is visible
    assert "Whip direction" in content
    assert "Party" in content
    # The admin link ID column should be visible for superusers
    assert f"/admin/votes/whipreport/{whip_report.id}/change/" in content
