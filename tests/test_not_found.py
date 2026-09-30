from django.test.client import Client

import pytest

pytestmark = pytest.mark.django_db


def test_missing_policy_page_is_404(client: Client):
    """
    A person-policy page for a policy that doesn't exist should 404, not 500.
    """
    response = client.get("/person/25878/policies/commons/conservative/all_time/999999")
    assert response.status_code == 404


def test_missing_policy_api_is_404(client: Client):
    """
    The API should return a JSON 404 for a missing object.
    """
    response = client.get("/policy/999999.json")
    assert response.status_code == 404
    assert "detail" in response.json()
