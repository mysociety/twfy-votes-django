import io

from django.test import Client

import pandas as pd
import pytest

pytestmark = pytest.mark.django_db


class BaseTestResponse:
    url: str = "/"
    status_code: int = 200
    must_contain: list[str] = []
    must_not_contain: list[str] = []
    has_json: bool = False

    def test_present(self, client: Client):
        response = client.get(self.url)
        assert response.status_code == self.status_code

        for item in self.must_contain:
            assert item in response.content.decode(), f"Missing {item}"

        for item in self.must_not_contain:
            assert item not in response.content.decode(), f"Unexpected {item}"

    def test_json(self, client: Client):
        if not self.has_json:
            return
        response = client.get(self.url + ".json")
        assert response.status_code == self.status_code
        assert response.json() is not None


class TestDivision2023(BaseTestResponse):
    url: str = "/decisions/division/commons/2023-12-13/33"
    status_code: int = 200
    must_contain: list[str] = []
    must_not_contain: list[str] = []

    def test_json(self, client: Client):
        """
        A basic test that the data remains consistent.

        This division was double checked with public whip.

        Only difference is us not highlighting the tellers as seperate.

        But saying tellers voted with their direction.

        May be something to come back to - not *always* the case.

        But is easier to make consistent with other parliaments.
        """
        response = client.get(self.url + ".json")
        assert response.status_code == self.status_code
        assert response.json() is not None

        data = response.json()

        overall_breakdown = data["overall_breakdowns"][0]

        assert overall_breakdown["for_motion"] == 288, "Expected 288 for votes"
        assert overall_breakdown["against_motion"] == 54, "Expected 54 against votes"

        party_breakdowns = data["party_breakdowns"]
        con_breakdown = [
            x for x in party_breakdowns if x["party_slug"] == "conservative"
        ][0]

        gov_breakdowns = data["is_gov_breakdowns"]
        gov = [x for x in gov_breakdowns if x["is_gov"] is True][0]

        assert con_breakdown["for_motion"] == 285, "Expected 285 for votes"
        assert gov["for_motion"] == 285, "Expected 285 for votes"

        assert len(data["votes"]) == (
            650
        ), f"Expected 650 votes (inc absents), got {len(data['votes'])}"


def test_voting_list():
    client = Client()
    url = "/decisions/division/commons/2023-12-13/33/voting_list.csv"

    response = client.get(url)

    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
    assert response.headers["Content-Type"] == "text/csv", "Expected CSV content type"

    file = io.StringIO(response.content.decode("utf-8"))
    df = pd.read_csv(file)
    assert not df.empty, "Expected non-empty DataFrame"

    assert "person_id" in df.columns, "Expected 'member_id' column in DataFrame"

    # check length is 650
    assert len(df) == 650, f"Expected 650 rows, got {len(df)}"
