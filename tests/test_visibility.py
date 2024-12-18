from django.contrib.auth.models import Group, User
from django.test import Client

import pytest

pytestmark = pytest.mark.django_db


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
    group = Group.objects.get(name="access_in_progress")
    user.groups.add(group)
    yield user
    user.delete()


def test_policies_restricted_not_loggedin(client: Client):
    response = client.get("/policies")
    assert response.status_code == 200
    assert "/policies/commons/draft/all" not in response.content.decode()


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
