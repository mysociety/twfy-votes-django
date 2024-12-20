from django.test import Client

import pytest

from votes.models import (
    Agreement,
    AgreementAnnotation,
    Division,
    DivisionAnnotation,
    VoteAnnotation,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def agreement_annotation():
    da = AgreementAnnotation(
        agreement=Agreement.objects.get(key="a-commons-2021-12-13-e.876.1.2"),
        detail="Link to BBC Sport",
        link="https://www.bbc.co.uk/sport",
    )
    da.save()
    yield da
    da.delete()


@pytest.fixture
def division_annotation():
    da = DivisionAnnotation(
        division=Division.objects.get(key="pw-2016-12-13-109-commons"),
        detail="Link to BBC News",
        link="https://www.bbc.co.uk/news",
    )
    da.save()
    yield da
    da.delete()


@pytest.fixture
def vote_annotation():
    va = VoteAnnotation(
        division=Division.objects.get(key="pw-2016-12-13-109-commons"),
        person_id=10001,
        detail="Link to Google",
        link="https://www.google.com",
    )
    va.save()
    yield va
    va.delete()


def test_original_data_agreement(client: Client):
    response = client.get("/decisions/agreement/commons/2021-12-13/e.876.1.2")
    content = response.content.decode()
    assert "Link to BBC Sport" not in content
    assert "https://www.bbc.co.uk/sport" not in content


def test_original_data_agreement_json(client: Client):
    response = client.get("/decisions/agreement/commons/2021-12-13/e.876.1.2.json")
    content = response.content.decode()
    assert "Link to BBC Sport" not in content
    assert "https://www.bbc.co.uk/sport" not in content


def test_agreement_annotation(
    client: Client, agreement_annotation: AgreementAnnotation
):
    response = client.get("/decisions/agreement/commons/2021-12-13/e.876.1.2")
    content = response.content.decode()
    assert "Link to BBC Sport" in content
    assert "https://www.bbc.co.uk/sport" in content


def test_agreement_annotation_json(
    client: Client, agreement_annotation: AgreementAnnotation
):
    response = client.get("/decisions/agreement/commons/2021-12-13/e.876.1.2.json")
    content = response.content.decode()
    assert "Link to BBC Sport" in content
    assert "https://www.bbc.co.uk/sport" in content


def test_original_data(client: Client):
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    for text in ["Link to BBC News", "Link to Google"]:
        assert text not in content
    for url in ["https://www.bbc.co.uk/news", "https://www.google.com"]:
        assert url not in content


def test_original_data_json(client: Client):
    response = client.get("/decisions/division/commons/2016-12-13/109.json")
    content = response.content.decode()
    for text in ["Link to BBC News", "Link to Google"]:
        assert text not in content
    for url in ["https://www.bbc.co.uk/news", "https://www.google.com"]:
        assert url not in content


def test_division_annotation(client: Client, division_annotation: DivisionAnnotation):
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    assert "Link to BBC News" in content
    assert "https://www.bbc.co.uk/news" in content
    assert "Link to Google" not in content
    assert "https://www.google.com" not in content


def test_division_annotation_json(
    client: Client, division_annotation: DivisionAnnotation
):
    response = client.get("/decisions/division/commons/2016-12-13/109.json")
    content = response.content.decode()
    assert "Link to BBC News" in content
    assert "https://www.bbc.co.uk/news" in content
    assert "Link to Google" not in content
    assert "https://www.google.com" not in content


def test_vote_annotation(client: Client, vote_annotation: VoteAnnotation):
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    assert "Link to BBC News" not in content
    assert "https://www.bbc.co.uk/news" not in content
    assert "Link to Google" in content
    assert "https://www.google.com" in content


def test_vote_annotation_json(client: Client, vote_annotation: VoteAnnotation):
    response = client.get("/decisions/division/commons/2016-12-13/109.json")
    content = response.content.decode()
    assert "Link to BBC News" not in content
    assert "https://www.bbc.co.uk/news" not in content
    assert "Link to Google" in content
    assert "https://www.google.com" in content


def test_division_and_vote_annotation(
    client: Client,
    division_annotation: DivisionAnnotation,
    vote_annotation: VoteAnnotation,
):
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    assert "Link to BBC News" in content
    assert "https://www.bbc.co.uk/news" in content
    assert "Link to Google" in content
    assert "https://www.google.com" in content


def test_division_and_vote_annotation_json(
    client: Client,
    division_annotation: DivisionAnnotation,
    vote_annotation: VoteAnnotation,
):
    response = client.get("/decisions/division/commons/2016-12-13/109.json")
    content = response.content.decode()
    assert "Link to BBC News" in content
    assert "https://www.bbc.co.uk/news" in content
    assert "Link to Google" in content
    assert "https://www.google.com" in content
