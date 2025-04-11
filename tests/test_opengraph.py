from django.test import Client

import pytest

from votes.models import Agreement, Division

pytestmark = pytest.mark.django_db


@pytest.fixture
def division_id():
    return Division.objects.get(key="pw-2016-12-13-109-commons").id


@pytest.fixture
def agreement_id():
    return Agreement.objects.get(key="a-commons-2024-12-19-b.564.3.2").id


def test_division_image(client: Client, division_id: int):
    response = client.get(f"/opengraph/division/{division_id}")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


def test_agreement_image(client: Client, agreement_id: int):
    response = client.get(f"/opengraph/agreement/{agreement_id}")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
