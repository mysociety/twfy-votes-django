from django.test import Client

import pytest

from votes.consts import EvidenceType, WhipDirection, WhipPriority
from votes.models import (
    Division,
    Organization,
    WhipReport,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def whip_report():
    da = WhipReport(
        division=Division.objects.get(key="pw-2016-12-13-109-commons"),
        whip_direction=WhipDirection.AGAINST,
        whip_priority=WhipPriority.THREE_LINE,
        party=Organization.objects.get(slug="labour"),
        evidence_type=EvidenceType.OTHER,
    )
    da.save()
    yield da
    da.delete()


def test_original_data(client: Client):
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    for text in ["against", "three_line"]:
        assert text not in content


def test_original_data_json(client: Client):
    response = client.get("/decisions/division/commons/2016-12-13/109.json")
    content = response.content.decode()
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    for text in ["against", "three_line"]:
        assert text not in content


def test_whip_report(client: Client, whip_report: WhipReport):
    response = client.get("/decisions/division/commons/2016-12-13/109")
    content = response.content.decode()
    for text in ["Whip reports", "against", "three_line"]:
        assert text in content


def test_whip_report_json(client: Client, whip_report: WhipReport):
    response = client.get("/decisions/division/commons/2016-12-13/109.json")
    data = response.json()
    assert len(data["whip_reports"]) > 0
    labour_whip = [x for x in data["whip_reports"] if x["party"] == "Labour"]
    assert len(labour_whip) == 1
    assert labour_whip[0]["whip_direction"] == "against"
    assert labour_whip[0]["whip_priority"] == "three_line"
