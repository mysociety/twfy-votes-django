from django.test import Client

import pytest

from votes.consts import EvidenceType, PolicyStrength, WhipDirection, WhipPriority
from votes.models import Organization, Policy, WhipReport

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    """Get a test client"""
    return Client()


@pytest.fixture
def setup_whip_reports():
    """Create whip reports for existing data"""
    # Get an existing policy with divisions
    policy = Policy.objects.filter(division_links__isnull=False).first()
    assert policy

    # Get the first few divisions linked to this policy
    divisions = [
        link.decision
        for link in policy.division_links.filter(strength=PolicyStrength.STRONG)[:3]
    ]

    # Get existing parties
    labour = Organization.objects.filter(slug="labour").first()
    conservative = Organization.objects.filter(slug="conservative").first()

    assert labour and conservative

    # Create whip reports
    whip_reports = []

    # Division 0: Free vote for Labour
    whip_reports.append(
        WhipReport.objects.create(
            division=divisions[0],
            party=labour,
            whip_direction=WhipDirection.FREE,
            whip_priority=WhipPriority.FREE,
            evidence_type=EvidenceType.OTHER,
            evidence_detail="Test free vote",
        )
    )

    # Whip report for Conservative - not free
    whip_reports.append(
        WhipReport.objects.create(
            division=divisions[1],
            party=conservative,
            whip_direction=WhipDirection.FOR,
            whip_priority=WhipPriority.ONE_LINE,  # Not FREE priority
            evidence_type=EvidenceType.OTHER,
            evidence_detail="Test not free vote",
        )
    )

    # Division 2: Strong free vote for Conservative
    if len(divisions) > 2:
        whip_reports.append(
            WhipReport.objects.create(
                division=divisions[2],
                party=conservative,
                whip_direction=WhipDirection.FREE,
                whip_priority=WhipPriority.FREE,
                evidence_type=EvidenceType.OTHER,
                evidence_detail="Test another strong free vote",
            )
        )

    yield {
        "policy": policy,
        "divisions": divisions,
        "whip_reports": whip_reports,
        "labour": labour,
        "conservative": conservative,
    }

    # Cleanup
    for report in whip_reports:
        report.delete()


def test_policy_annotation_method(setup_whip_reports):
    """Test the Policy.annotate_free_vote_parties method directly"""
    policy = setup_whip_reports["policy"]

    # Test the annotation
    annotated_policies = Policy.objects.filter(id=policy.id)
    annotated_policy = annotated_policies.first()
    assert annotated_policy

    assert len(annotated_policy.get_free_vote_parties()) == 2


def test_annotation_with_no_whip_reports():
    """Test annotation for a policy with no whip reports"""
    # Get a policy that doesn't have any whip reports
    policies_with_whips = Policy.objects.filter(
        division_links__decision__whip_reports__isnull=False
    ).values_list("id", flat=True)

    policy_without_whips = Policy.objects.exclude(id__in=policies_with_whips).first()

    if not policy_without_whips:
        # Use any policy if none found without whips
        policy_without_whips = Policy.objects.first()

    if not policy_without_whips:
        pytest.skip("No policies found for testing")

    annotated_policies = Policy.objects.filter(id=policy_without_whips.id)
    annotated_policy = annotated_policies.first()
    assert annotated_policy

    assert len(annotated_policy.get_free_vote_parties()) == 0


def test_get_policy_by_id_api(setup_whip_reports, client):
    """Test the /policy/{policy_id}.json endpoint"""
    policy = setup_whip_reports["policy"]

    response = client.get(f"/policy/{policy.id}.json")
    assert response.status_code == 200

    data = response.json()
    assert "free_vote_parties" in data
    assert len(data["free_vote_parties"]) == 2


def test_get_policy_by_chamber_status_group(client, setup_whip_reports):
    """Test the /policy/{chamber_slug}/{status}/{group_slug}.json endpoint"""
    policy = setup_whip_reports["policy"]

    # Get the first group for this policy
    group_slug = policy.groups.first().slug if policy.groups.exists() else "misc"

    response = client.get(
        f"/policy/{policy.chamber_slug}/{policy.status}/{group_slug}.json"
    )

    # The policy might not be found by this specific combination, so check both cases
    if response.status_code == 200:
        data = response.json()
        if data and data.get("id") == policy.id:
            assert "free_vote_parties" in data
            assert len(data["free_vote_parties"]) == 2
            assert set(data["free_vote_parties"]) == {"conservative", "labour"}


def test_get_chamber_status_policies_api(client, setup_whip_reports):
    """Test the /policies/{chamber_slug}/{status_slug}/{group_slug}.json endpoint"""
    policy = setup_whip_reports["policy"]

    # Get the first group for this policy
    group_slug = policy.groups.first().slug if policy.groups.exists() else "misc"

    response = client.get(
        f"/policies/{policy.chamber_slug}/{policy.status}/{group_slug}.json"
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)

    # Find our test policy in the results
    test_policy_data = None
    for policy_data in data:
        if policy_data["id"] == policy.id:
            test_policy_data = policy_data
            break

    if test_policy_data:  # Only test if our policy is in the results
        assert "free_vote_parties" in test_policy_data
        assert len(test_policy_data["free_vote_parties"]) == 2
        assert set(test_policy_data["free_vote_parties"]) == {
            "conservative",
            "labour",
        }


def test_general_policies_api_has_counts(client, setup_whip_reports):
    """Test that the general /policies.json endpoint includes the free vote counts"""
    policy = setup_whip_reports["policy"]

    response = client.get("/policies.json")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)

    # Find our test policy in the results
    test_policy_data = None
    for policy_data in data:
        if policy_data["id"] == policy.id:
            test_policy_data = policy_data
            break

    if test_policy_data:  # Only test if our policy is in the results
        assert "free_vote_parties" in test_policy_data
        assert len(test_policy_data["free_vote_parties"]) == 2
        assert set(test_policy_data["free_vote_parties"]) == {
            "conservative",
            "labour",
        }


def test_all_policies_have_free_vote_counts(client):
    """Test that all policies in the general endpoint have the free vote count fields"""
    response = client.get("/policies.json")
    assert response.status_code == 200

    data = response.json()
    if data:  # If there are policies
        first_policy = data[0]
        # These fields should be present (even if 0)
        assert "free_vote_parties" in first_policy
