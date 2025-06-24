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
def test_statement_power_user():
    """Create a user with statement creation permissions"""
    user = User.objects.create_user(username="teststatement", password="password")
    group = Group.objects.get(name=PermissionGroupSlug.CAN_ADD_STATEMENT)
    user.groups.add(group)
    yield user
    user.delete()


@pytest.fixture
def test_regular_user():
    """Create a regular user without special permissions"""
    user = User.objects.create_user(username="regularuser", password="password")
    yield user
    user.delete()


def test_statement_form_visible_anonymous(client: Client):
    """Anonymous users should not be able to access the statement form"""
    response = client.get("/submit/statement")
    assert response.status_code == 403


def test_statement_form_visible_regular_user(client: Client, test_regular_user: User):
    """Regular users without permissions should not be able to access the statement form"""
    client.force_login(test_regular_user)
    response = client.get("/submit/statement")
    assert response.status_code == 403


def test_statement_form_visible_superuser(client: Client, test_super_user: User):
    """Superusers should be able to access the statement form"""
    client.force_login(test_super_user)
    response = client.get("/submit/statement")
    assert response.status_code == 200
    assert "Add Statement Form" in response.content.decode()


def test_statement_form_visible_permission_user(
    client: Client, test_statement_power_user: User
):
    """Users with statement permissions should be able to access the statement form"""
    client.force_login(test_statement_power_user)
    response = client.get("/submit/statement")
    assert response.status_code == 200
    assert "Add Statement Form" in response.content.decode()


def test_statement_form_submission_valid_data(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test successful statement form submission with valid data"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "Test Statement",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,
        "statement_type": StatementType.PROPOSED_MOTION.value,
        "url": "https://example.com/test-statement",
        "content": "This is a test statement content with detailed information.",
        "signatories": "Diane Abbott\nJeremy Corbyn\nEd Miliband",
    }

    response = client.post("/submit/statement", form_data)

    # Should redirect to the statement page
    assert response.status_code == 302

    # Check that the statement was created
    statement = Statement.objects.filter(title="Test Statement").first()
    assert statement is not None
    assert statement.chamber_id == commons_chamber.id
    assert (
        statement.statement_text
        == "This is a test statement content with detailed information."
    )
    assert statement.type == StatementType.PROPOSED_MOTION
    assert statement.url == "https://example.com/test-statement"
    assert statement.date == date(2023, 6, 15)

    # Check that signatures were created
    signatures = Signature.objects.filter(statement_id=statement.id)
    assert signatures.count() == 3

    # Check that we got a redirect (statement was created successfully)
    assert response.status_code == 302


def test_statement_form_submission_missing_signatories(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test statement form submission without signatories"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "Test Statement No Signatories",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,
        "statement_type": StatementType.PROPOSED_MOTION.value,
        "content": "This is a test statement without signatories.",
        "signatories": "",  # Empty signatories
    }

    response = client.post("/submit/statement", form_data)

    # Should return form with errors
    assert response.status_code == 200
    assert "At least one signatory is required" in response.content.decode()

    # Check that no statement was created
    statement = Statement.objects.filter(title="Test Statement No Signatories").first()
    assert statement is None


def test_statement_form_submission_invalid_signatory(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test statement form submission with invalid signatory name"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "Test Statement Invalid Signatory",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,
        "statement_type": StatementType.PROPOSED_MOTION.value,
        "content": "This is a test statement with invalid signatory.",
        "signatories": "Diane Abbott\nInvalid Person Name\nJeremy Corbyn",
    }

    response = client.post("/submit/statement", form_data)

    # Should return form with errors
    assert response.status_code == 200
    assert "Could not find person" in response.content.decode()
    assert "Invalid Person Name" in response.content.decode()

    # Check that no statement was created
    statement = Statement.objects.filter(
        title="Test Statement Invalid Signatory"
    ).first()
    assert statement is None


def test_statement_form_submission_missing_required_fields(
    client: Client, test_super_user: User
):
    """Test statement form submission with missing required fields"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "",  # Missing title
        "date": "",  # Missing date
        "chamber": "",  # Missing chamber
        "statement_type": "",  # Missing type
        "content": "",  # Missing content
        "signatories": "Diane Abbott",
    }

    response = client.post("/submit/statement", form_data)

    # Should return form with errors
    assert response.status_code == 200
    content = response.content.decode()
    assert "This field is required" in content


def test_statement_form_submission_permission_denied(
    client: Client, test_regular_user: User, commons_chamber: Chamber
):
    """Test that users without permissions can't submit the form"""
    client.force_login(test_regular_user)

    form_data = {
        "statement_title": "Unauthorized Statement",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,
        "statement_type": StatementType.PROPOSED_MOTION.value,
        "content": "This should not be saved.",
        "signatories": "Diane Abbott",
    }

    response = client.post("/submit/statement", form_data)

    # Should get 404 due to permission check
    assert response.status_code == 403

    # Check that no statement was created
    statement = Statement.objects.filter(title="Unauthorized Statement").first()
    assert statement is None


def test_statement_form_submission_with_optional_url(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test statement form submission without optional URL field"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "Statement Without URL",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,
        "statement_type": StatementType.LETTER.value,
        "content": "This statement has no URL.",
        "signatories": "Diane Abbott",
    }

    response = client.post("/submit/statement", form_data)

    # Should redirect successfully
    assert response.status_code == 302

    # Check that the statement was created without URL
    statement = Statement.objects.filter(title="Statement Without URL").first()
    assert statement is not None
    assert statement.url == ""


def test_statement_form_submission_multiple_types(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test statement form submission with different statement types"""
    client.force_login(test_super_user)

    for statement_type in [
        StatementType.PROPOSED_MOTION,
        StatementType.LETTER,
        StatementType.OTHER,
    ]:
        form_data = {
            "statement_title": f"Test {statement_type.value} Statement",
            "date": "2023-06-15",
            "chamber": commons_chamber.id,
            "statement_type": statement_type.value,
            "content": f"This is a {statement_type.value} statement.",
            "signatories": "Diane Abbott",
        }

        response = client.post("/submit/statement", form_data)
        assert response.status_code == 302

        statement = Statement.objects.filter(
            title=f"Test {statement_type.value} Statement"
        ).first()
        assert statement is not None
        assert statement.type == statement_type


def test_statement_form_fields_rendered(client: Client, test_super_user: User):
    """Test that all form fields are properly rendered"""
    client.force_login(test_super_user)
    response = client.get("/submit/statement")
    assert response.status_code == 200

    content = response.content.decode()

    # Check for form fields
    assert 'name="statement_title"' in content
    assert 'name="date"' in content
    assert 'name="chamber"' in content
    assert 'name="statement_type"' in content
    assert 'name="url"' in content
    assert 'name="content"' in content
    assert 'name="signatories"' in content

    # Check for form labels
    assert "Title" in content
    assert "Date" in content
    assert "Chamber" in content
    assert "Statement Type" in content
    assert "Source URL" in content
    assert "Statement Content" in content
    assert "Signatories" in content


def test_statement_form_submission_former_mp_signatory(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test statement form submission with signatory who was an MP in a previous session but isn't current"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "Test Statement Former MP",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,
        "statement_type": StatementType.PROPOSED_MOTION,
        "content": "This statement includes a former MP as signatory.",
        # Using a date when they might not be current - this should test the edge case
        # of someone who was an MP in previous sessions
        "signatories": "Diane Abbott\nTony Blair",  # Assuming 'Former MP Name' is someone who was an MP but isn't current
    }

    response = client.post("/submit/statement", form_data)

    # Should return form with errors for the former MP who can't be found for this date
    assert response.status_code == 200
    content = response.content.decode()
    assert "Could not find person" in content or response.status_code == 302


def test_statement_form_submission_other_chamber_member(
    client: Client, test_super_user: User, commons_chamber: Chamber
):
    """Test statement form submission with signatory who is a member of a different chamber"""
    client.force_login(test_super_user)

    form_data = {
        "statement_title": "Test Statement Other Chamber",
        "date": "2023-06-15",
        "chamber": commons_chamber.id,  # Commons chamber
        "statement_type": StatementType.LETTER,
        "content": "This statement attempts to include a MSP member as signatory to a Commons statement.",
        # Trying to add someone who is in Lords to a Commons statement
        "signatories": "Diane Abbott\nKaren Adam",
    }

    response = client.post("/submit/statement", form_data)

    # Should return form with errors for the Lords member who shouldn't sign Commons statements
    assert response.status_code == 200
    content = response.content.decode()
    assert "Could not find person" in content
