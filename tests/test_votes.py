from django.test.client import Client

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


class TestIndex(BaseTestResponse):
    url = "/"


class TestPersons(BaseTestResponse):
    url = "/persons"
    status_code = 404


class TestCurrentPeople(BaseTestResponse):
    url = "/people/current"
    has_json = True


class TestAllPeople(BaseTestResponse):
    url = "/people/all"
    has_json = True


class TestPerson(BaseTestResponse):
    url = "/person/10001"
    has_json = True


class TestPolicies(BaseTestResponse):
    url = "/policies"
    has_json = True


class TestActiveCommonsPolicies(BaseTestResponse):
    url = "/policies/commons/active/all"
    has_json = True


class TestCandidateCommonsPolicies(BaseTestResponse):
    url = "/policies/commons/candidate/all"
    has_json = True


class TestPolicy(BaseTestResponse):
    url = "/policy/6679"
    has_json = True


class TestDecisions(BaseTestResponse):
    url = "/decisions"
    has_json = False


class TestDivision(BaseTestResponse):
    url = "/decisions/division/commons/2023-10-17/328"
    has_json = True


class TestDivisionsYear(BaseTestResponse):
    url = "/decisions/commons/2023"
    has_json = True


class TestDivisionsMonth(BaseTestResponse):
    url = "/decisions/commons/2023/10"
    has_json = True


class TestAgreementInfo(BaseTestResponse):
    url = "/decisions/agreement/commons/2019-06-24/b.530.1.2"
    has_json = True


class TestPersonPolicies(BaseTestResponse):
    url = "/person/10001/policies/commons/labour/all_time"
    has_json = True


class TestPersonPolicy(BaseTestResponse):
    url = "/person/10001/policies/commons/labour/all_time/363"
    has_json = True


class TestPersonStatements(BaseTestResponse):
    url = "/person/25846/statements"
    has_json = True


class TestStatement(BaseTestResponse):
    url = "/statement/commons/2015-01-05/london-housing-and-foreign-investors"
    has_json = True  # API endpoint is at statements/{chamber_slug}/{date}/{slug}.json


class TestStatements(BaseTestResponse):
    url = "/statements"
    has_json = False


class TestStatementsYear(BaseTestResponse):
    url = "/statements/commons/2015"
    has_json = True


class TestStatementsMonth(BaseTestResponse):
    url = "/statements/commons/2015/1"
    has_json = True


class TestTagHome(BaseTestResponse):
    url = "/tags"
    has_json = True


class TestSingleTagTypeHome(BaseTestResponse):
    url = "/tags/gov_clusters"
    has_json = True


class TestTag(BaseTestResponse):
    url = "/tags/gov_clusters/cross_party_aye"
    has_json = True


def test_statement_api_endpoint(client: Client):
    """Test that the statement API endpoint works correctly"""
    response = client.get(
        "/statement/commons/2015-01-05/london-housing-and-foreign-investors.json"
    )
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]

    data = response.json()
    assert "title" in data
    assert "signatures" in data
    assert "url" in data


def test_statements_year_api_performance(client: Client):
    """Test that the statements year API is performant and returns signature counts"""
    response = client.get("/statements/commons/2015.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]

    data = response.json()
    assert isinstance(data, list)
    if data:  # If there are statements
        statement = data[0]
        assert "signature_count" in statement
        assert "nice_title" in statement
        assert "type_display" in statement
        assert "url" in statement


def test_statements_month_api_performance(client: Client):
    """Test that the statements month API is performant and returns signature counts"""
    response = client.get("/statements/commons/2015/1.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]

    data = response.json()
    assert isinstance(data, list)
    if data:  # If there are statements
        statement = data[0]
        assert "signature_count" in statement
        assert isinstance(statement["signature_count"], int)


def test_vote_popolo(client: Client):
    response = client.get("/twfy-compatible/popolo/6679.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]


def test_vote_participants_2005(client: Client):
    response = client.get("/decisions/division/commons/2005-11-22/105.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]

    data = response.json()

    assert data["overall_breakdowns"][0]["total_possible_members"] == 646


def test_vote_participants_2015(client: Client):
    response = client.get("/decisions/division/commons/2015-12-08/145.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]

    data = response.json()

    assert data["overall_breakdowns"][0]["total_possible_members"] == 650


def test_all_popolo_policies(client: Client):
    """
    Check all popolo policies are valid for the commons active list.
    This one takes a bit of time, but catches all errors that would stump the
    TheyWorkForYou importer.
    Given this is the most important bridging function.
    """
    response = client.get("/policies/commons/active/all.json")
    data = response.json()

    policy_ids = [policy["id"] for policy in data]
    for p in policy_ids:
        response = client.get(f"/twfy-compatible/popolo/{p}.json")
        assert response.status_code == 200, f"Failed on {p}"
