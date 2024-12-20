from django.test import Client

import pytest

from votes.models import AnalysisOverride

pytestmark = pytest.mark.django_db


@pytest.fixture
def override():
    ao = AnalysisOverride(
        decision_key="pw-2024-12-03-52-commons",
        banned_motion_ids="uk.org.publicwhip/debate/2024-12-03b.193.2.1",
        parl_dynamics_group="free_vote",
        manual_parl_dynamics_desc="Manual text",
    )
    ao.save()
    yield ao
    ao.delete()


def test_original_data(client: Client):
    response = client.get("/decisions/division/commons/2024-12-03/52")
    content = response.content.decode()
    assert (
        "That leave be given to bring in a Bill to introduce a system of proportional representation"
        in content
    )
    assert "Low participation vote" in content


def test_original_data_json(client: Client):
    response = client.get("/decisions/division/commons/2024-12-03/52.json")
    content = response.content.decode()
    assert (
        "That leave be given to bring in a Bill to introduce a system of proportional representation"
        in content
    )
    assert "Low participation vote" in content


def test_with_override(client: Client, override: AnalysisOverride):
    response = client.get("/decisions/division/commons/2024-12-03/52")
    content = response.content.decode()
    assert (
        "That leave be given to bring in a Bill to introduce a system of proportional representation"
        not in content
    )
    assert "Low participation vote" not in content
    assert "Manual text" in content
    assert "Free vote" in content


def test_with_override_json(client: Client, override: AnalysisOverride):
    response = client.get("/decisions/division/commons/2024-12-03/52.json")
    content = response.content.decode()
    assert (
        "That leave be given to bring in a Bill to introduce a system of proportional representation"
        not in content
    )
    assert "Low participation vote" not in content
    assert "Manual text" in content
    assert "Free vote" in content
