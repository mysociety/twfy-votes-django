from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client

import pytest

from votes.consts import PermissionGroupSlug, StatementType
from votes.models import Chamber, Signature, Statement

pytestmark = pytest.mark.django_db


@pytest.fixture
def commons_chamber():
    """Get the Commons chamber for testing"""
    return Chamber.objects.get(slug="commons")


@pytest.fixture
def test_super_user():
    """Create a superuser for testing"""
    user = User.objects.create_user(
        username="testuser", password="password", is_superuser=True
    )
    yield user
    user.delete()


@pytest.fixture
def test_signatories_power_user():
    """Create a user with add signatories permissions"""
    user = User.objects.create_user(username="testsignatories", password="password")
    group = Group.objects.get(name=PermissionGroupSlug.CAN_ADD_SIGNATORIES)
    user.groups.add(group)
    yield user
    user.delete()


@pytest.fixture
def test_regular_user():
    """Create a regular user without special permissions"""
    user = User.objects.create_user(username="regularuser", password="password")
    yield user
    user.delete()


@pytest.fixture
def test_statement(commons_chamber):
    """Create a test statement with initial signatories"""
    statement = Statement.objects.create(
        key="test-statement-2023-06-15",
        chamber_slug=commons_chamber.slug,
        chamber_id=commons_chamber.id,
        title="Test Statement for Signatories",
        slug="test-statement-for-signatories",
        statement_text="This is a test statement for adding signatories.",
        date=date(2023, 6, 15),
        type=StatementType.PROPOSED_MOTION,
        url="",
        extra_info={},
    )

    # Add initial signature
    Signature.objects.create(
        key=f"{statement.key}-10001",
        statement_id=statement.id,
        person_id=10001,  # Diane Abbott
        date=date(2023, 6, 15),
        order=0,
        extra_info={},
    )

    yield statement
    statement.delete()


def test_add_signatories_form_visible_anonymous(
    client: Client, test_statement: Statement
):
    """Anonymous users should not be able to access the add signatories form"""
    response = client.get(f"/submit/add_signatories/{test_statement.id}")
    assert response.status_code == 403


def test_add_signatories_form_visible_regular_user(
    client: Client, test_regular_user: User, test_statement: Statement
):
    """Regular users without permissions should not be able to access the add signatories form"""
    client.force_login(test_regular_user)
    response = client.get(f"/submit/add_signatories/{test_statement.id}")
    assert response.status_code == 403


def test_add_signatories_form_visible_superuser(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Superusers should be able to access the add signatories form"""
    client.force_login(test_super_user)
    response = client.get(f"/submit/add_signatories/{test_statement.id}")
    assert response.status_code == 200
    assert "Add Signatories to Statement" in response.content.decode()


def test_add_signatories_form_visible_permission_user(
    client: Client, test_signatories_power_user: User, test_statement: Statement
):
    """Users with add signatories permissions should be able to access the form"""
    client.force_login(test_signatories_power_user)
    response = client.get(f"/submit/add_signatories/{test_statement.id}")
    assert response.status_code == 200
    assert "Add Signatories to Statement" in response.content.decode()


def test_add_signatories_form_submission_valid_data(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test successful add signatories form submission with valid data"""
    client.force_login(test_super_user)

    # Check initial signature count
    initial_count = Signature.objects.filter(statement=test_statement).count()
    assert initial_count == 1

    form_data = {
        "statement_id": test_statement.id,
        "date": "2023-06-16",
        "signatories": "Jeremy Corbyn\nEd Miliband",
    }

    response = client.post(f"/submit/add_signatories/{test_statement.id}", form_data)

    # Should redirect to the statement page
    assert response.status_code == 302

    # Check that new signatures were created
    final_count = Signature.objects.filter(statement=test_statement).count()
    assert final_count == 3  # 1 initial + 2 new

    # Check that the order is correct
    signatures = Signature.objects.filter(statement=test_statement).order_by("order")
    assert signatures[0].order == 0  # Original signature
    assert signatures[1].order == 1  # First new signature
    assert signatures[2].order == 2  # Second new signature


def test_add_signatories_form_submission_missing_signatories(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test add signatories form submission without signatories"""
    client.force_login(test_super_user)

    form_data = {
        "statement_id": test_statement.id,
        "date": "2023-06-16",
        "signatories": "",  # Empty signatories
    }

    response = client.post(f"/submit/add_signatories/{test_statement.id}", form_data)

    # Should return form with errors
    assert response.status_code == 200
    assert "At least one signatory is required" in response.content.decode()

    # Check that no new signatures were created
    count = Signature.objects.filter(statement=test_statement).count()
    assert count == 1  # Only the initial signature


def test_add_signatories_form_submission_invalid_signatory(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test add signatories form submission with invalid signatory name"""
    client.force_login(test_super_user)

    form_data = {
        "statement_id": test_statement.id,
        "date": "2023-06-16",
        "signatories": "Jeremy Corbyn\nInvalid Person Name\nEd Miliband",
    }

    response = client.post(f"/submit/add_signatories/{test_statement.id}", form_data)

    # Should return form with errors
    assert response.status_code == 200
    assert "Could not find person" in response.content.decode()
    assert "Invalid Person Name" in response.content.decode()

    # Check that no new signatures were created
    count = Signature.objects.filter(statement=test_statement).count()
    assert count == 1  # Only the initial signature


def test_add_signatories_form_submission_duplicate_signatory(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test add signatories form submission with duplicate signatory"""
    client.force_login(test_super_user)

    form_data = {
        "statement_id": test_statement.id,
        "date": "2023-06-16",
        "signatories": "Diane Abbott\nJeremy Corbyn",  # Diane Abbott already signed
    }

    response = client.post(f"/submit/add_signatories/{test_statement.id}", form_data)

    # Should return form with errors
    assert response.status_code == 200
    assert "has already signed this statement" in response.content.decode()

    # Check that no new signatures were created
    count = Signature.objects.filter(statement=test_statement).count()
    assert count == 1  # Only the initial signature


def test_add_signatories_form_submission_permission_denied(
    client: Client, test_regular_user: User, test_statement: Statement
):
    """Test that users without permissions can't submit the form"""
    client.force_login(test_regular_user)

    form_data = {
        "statement_id": test_statement.id,
        "date": "2023-06-16",
        "signatories": "Jeremy Corbyn",
    }

    response = client.post(f"/submit/add_signatories/{test_statement.id}", form_data)

    # Should get 403 due to permission check
    assert response.status_code == 403

    # Check that no new signatures were created
    count = Signature.objects.filter(statement=test_statement).count()
    assert count == 1  # Only the initial signature


def test_add_signatories_form_fields_rendered(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test that all form fields are properly rendered"""
    client.force_login(test_super_user)
    response = client.get(f"/submit/add_signatories/{test_statement.id}")
    assert response.status_code == 200

    content = response.content.decode()

    # Check for form fields
    assert 'name="statement_id"' in content
    assert 'name="date"' in content
    assert 'name="signatories"' in content

    # Check for form labels and help text
    assert "Signature Date" in content
    assert "New Signatories" in content
    assert "one name per line" in content


def test_add_signatories_link_visible_on_statement_page(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test that the add signatories link is visible on the statement page for authorized users"""
    client.force_login(test_super_user)

    statement_url = f"/statement/{test_statement.chamber_slug}/{test_statement.date}/{test_statement.slug}"
    response = client.get(statement_url)
    assert response.status_code == 200

    content = response.content.decode()
    assert "Add Signatories" in content
    assert f"/submit/add_signatories/{test_statement.id}" in content


def test_add_signatories_link_not_visible_for_unauthorized_users(
    client: Client, test_regular_user: User, test_statement: Statement
):
    """Test that the add signatories link is not visible for unauthorized users"""
    client.force_login(test_regular_user)

    statement_url = f"/statement/{test_statement.chamber_slug}/{test_statement.date}/{test_statement.slug}"
    response = client.get(statement_url)
    assert response.status_code == 200

    content = response.content.decode()
    assert "Add Signatories" not in content
    assert f"/submit/add_signatories/{test_statement.id}" not in content


def test_add_signatories_form_submission_duplicate_name_in_list(
    client: Client, test_super_user: User, test_statement: Statement
):
    """Test add signatories form submission with the same name listed twice"""
    client.force_login(test_super_user)

    form_data = {
        "statement_id": test_statement.id,
        "date": "2023-06-16",
        "signatories": "Jeremy Corbyn\nEd Miliband\nJeremy Corbyn",  # Jeremy Corbyn listed twice
    }

    response = client.post(f"/submit/add_signatories/{test_statement.id}", form_data)

    # Should return form with errors
    assert response.status_code == 200
    assert "Duplicate signatory" in response.content.decode()

    # Check that no new signatures were created
    count = Signature.objects.filter(statement=test_statement).count()
    assert count == 1  # Only the initial signature
