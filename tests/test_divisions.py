from django.test import Client

import pytest

pytestmark = pytest.mark.django_db


class TestDivision2023:
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

        overall_breakdown = data["breakdowns"][0]

        assert overall_breakdown["for_motion"] == 290, "Expected 290 for votes"
        assert overall_breakdown["against_motion"] == 56, "Expected 56 against votes"

        party_breakdowns = data["party_breakdowns"]
        con_breakdown = [
            x for x in party_breakdowns if x["party_slug"] == "conservative"
        ][0]

        gov_breakdowns = data["is_gov_breakdowns"]
        gov = [x for x in gov_breakdowns if x["is_gov"] is True][0]

        assert con_breakdown["for_motion"] == 287, "Expected 287 for votes"
        assert gov["for_motion"] == 287, "Expected 287 for votes"

        assert len(data["votes"]) == (
            650
        ), f"Expected 650 votes (inc absents), got {len(data['votes'])}"
