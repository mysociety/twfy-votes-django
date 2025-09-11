from django.test import Client

import pytest

from votes.models import Agreement, DecisionTag, Division, Person, Policy, Statement

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


def test_general_image(client: Client):
    response = client.get("/opengraph/misc/home")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


@pytest.fixture
def person_id():
    person = Person.objects.first()
    if person:
        return person.id
    # Skip test if no person exists
    pytest.skip("No persons in database")


@pytest.fixture
def policy_id():
    policy = Policy.objects.first()
    if policy:
        return policy.id
    # Skip test if no policy exists
    pytest.skip("No policies in database")


@pytest.fixture
def statement_id():
    statement = Statement.objects.first()
    if statement:
        return statement.id
    # Skip test if no statement exists
    pytest.skip("No statements in database")


@pytest.fixture
def tag():
    tag = DecisionTag.objects.first()
    if tag:
        return (tag.tag_type, tag.slug)
    # Skip test if no tag exists
    pytest.skip("No tags in database")


def test_person_image(client: Client, person_id: int):
    response = client.get(f"/opengraph/person/{person_id}")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


def test_policy_image(client: Client, policy_id: int):
    response = client.get(f"/opengraph/policy/{policy_id}")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


def test_tag_image(client: Client, tag):
    tag_type, tag_slug = tag
    response = client.get(f"/opengraph/tag/{tag_type}/{tag_slug}")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


def test_statement_image(client: Client, statement_id: int):
    response = client.get(f"/opengraph/statement/{statement_id}")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
