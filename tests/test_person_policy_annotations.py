from django.test import Client

import pytest

from votes.models import Division, VoteAnnotation
from votes.views.views import PersonPolicyView

pytestmark = pytest.mark.django_db


@pytest.fixture
def person_policy_vote_annotation():
    """Create a vote annotation for testing person policy page annotations."""
    va = VoteAnnotation(
        division=Division.objects.get(key="pw-2016-12-13-109-commons"),
        person_id=10001,  # Diane Abbott
        detail="Statement on neighbourhood planning",
        link="https://example.com/diane-abbott-statement",
    )
    va.save()
    yield va
    va.delete()


def test_person_policy_page_without_annotations(client: Client):
    """Test that the person policy page works correctly when there are no annotations."""
    # Test the page for Diane Abbott on Powers of Local Councils policy
    response = client.get("/person/10001/policies/commons/labour/all_time/6695")

    assert response.status_code == 200
    content = response.content.decode()

    # Should not show annotation section when there are no annotations
    assert "Public statements and annotations" not in content


def test_person_policy_page_with_annotations(
    client: Client, person_policy_vote_annotation: VoteAnnotation
):
    """Test that the person policy page correctly displays annotations when they exist."""
    # Test the page for Diane Abbott on Powers of Local Councils policy
    response = client.get("/person/10001/policies/commons/labour/all_time/6695")

    assert response.status_code == 200
    content = response.content.decode()

    # Should show annotation section when there are annotations
    assert "Public statements and annotations" in content
    assert "Statement on neighbourhood planning" in content
    assert "https://example.com/diane-abbott-statement" in content

    # Should show the division name as a link
    assert "Neighbourhood Planning Bill" in content

    # Check that annotation column guide is shown in divisions when annotations exist
    assert "annotation: links to public statements" in content


def test_person_policy_view_context_without_annotations():
    """Test the PersonPolicyView context data when there are no annotations."""
    view = PersonPolicyView()

    context = view.get_context_data(
        person_id=10001,  # Diane Abbott
        chamber_slug="commons",
        party_slug="labour",
        period_slug="all_time",
        policy_id=6695,  # Powers of Local Councils
    )

    # Should have empty annotations list
    assert "person_annotations" in context
    assert context["person_annotations"] == []

    # Check that dataframes do not have annotation column
    decision_data = context["decision_links_and_votes"]
    for group_name, df in decision_data.items():
        if len(df) > 0:
            assert "annotation" not in df.columns


def test_person_policy_view_context_with_annotations(
    person_policy_vote_annotation: VoteAnnotation,
):
    """Test the PersonPolicyView context data when annotations exist."""
    view = PersonPolicyView()

    context = view.get_context_data(
        person_id=10001,  # Diane Abbott
        chamber_slug="commons",
        party_slug="labour",
        period_slug="all_time",
        policy_id=6695,  # Powers of Local Councils
    )

    # Should have annotations list with our test annotation
    assert "person_annotations" in context
    annotations = context["person_annotations"]
    assert len(annotations) == 1

    annotation = annotations[0]
    assert (
        annotation["division_name"]
        == person_policy_vote_annotation.division.division_name
    )
    assert annotation["annotation_html"] == person_policy_vote_annotation.html()
    assert "https://example.com/diane-abbott-statement" in annotation["annotation_html"]
    assert "Statement on neighbourhood planning" in annotation["annotation_html"]

    # Check that only the votes dataframe has the annotation column
    decision_data = context["decision_links_and_votes"]
    votes_df = decision_data["weak_votes"]
    if len(votes_df) > 0:
        assert "annotation" in votes_df.columns
