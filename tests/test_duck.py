from pathlib import Path
from unittest.mock import patch

from django.core.files import File
from django.http import FileResponse
from django.shortcuts import redirect as django_redirect
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

import duckdb
import pytest

from votes.models import BulkAPIUser

pytestmark = pytest.mark.django_db


@pytest.fixture
def bulk_api_user():
    """
    Create a BulkAPIUser
    """
    user = BulkAPIUser.objects.create(
        email="test@example.com", purpose="Testing", created_at=timezone.now()
    )
    yield user
    user.delete()


@pytest.fixture
def test_duckdb_file(tmp_path):
    """
    Create a test DuckDB file for testing
    """
    # Create the static/data directory structure
    data_dir = tmp_path / "static" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create a test DuckDB file
    db_path = data_dir / "twfy_votes.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO test VALUES (1, 'test')")
    conn.close()

    return tmp_path, db_path


@pytest.fixture
def static_settings(test_duckdb_file: tuple[Path, Path]):
    """
    Set up Django settings to use our test static files
    """
    static_root, db_file = test_duckdb_file

    def mock_redirect(url: str):
        """
        For patching the redirect function
        """
        # If it's the static URL for the DuckDB file
        # return our test file path
        if url == "/static/data/twfy_votes.duckdb":
            # Open the file in binary mode and create a Django File object
            file_obj = open(db_file, "rb")
            django_file = File(file_obj)

            # Create a FileResponse with the file
            response = FileResponse(django_file)
            response["Content-Disposition"] = 'attachment; filename="twfy_votes.duckdb"'
            return response
        # Otherwise, do a normal redirect

        return django_redirect(url)

    # Override Django settings for static files
    with override_settings(
        STATIC_ROOT=static_root,
        STATIC_URL="/static/",
        STATICFILES_DIRS=[],
        STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"],
    ):
        # Patch the redirect function in the views module
        with patch("votes.views.views.redirect", mock_redirect):
            yield static_root, db_file


def test_token_generation(bulk_api_user: BulkAPIUser):
    """Test that the BulkAPIUser has a token generated"""
    assert bulk_api_user.token is not None, "Token should be automatically generated"
    assert len(bulk_api_user.token) == 32, "Token should be 32 characters long"


def test_duck_download_without_token(client: Client):
    """Test that the duck download endpoint requires a token"""
    response = client.get(reverse("duckdb_download"))
    assert response.status_code == 401
    assert "error" in response.json()
    assert response.json()["error"] == "Authentication token required"


def test_duck_download_with_wrong_token(client: Client):
    """Test that the duck download endpoint rejects invalid tokens"""
    response = client.get(f"{reverse('duckdb_download')}?token=invalid_token")
    assert response.status_code == 401
    assert "error" in response.json()
    assert response.json()["error"] == "Invalid authentication token"


def test_duck_download_with_valid_token(
    client: Client, bulk_api_user: BulkAPIUser, static_settings: tuple[Path, Path]
):
    """Test that the duck download endpoint works with a valid token"""
    # Get the initial access count
    initial_access_count = bulk_api_user.access_count

    # Make the request with a valid token
    response = client.get(f"{reverse('duckdb_download')}?token={bulk_api_user.token}")

    # The response should either be a redirect to the static file or a direct file response
    assert response.status_code in [
        200,
        302,
    ], f"Unexpected status code: {response.status_code}"

    # Refresh the user from the database to get the updated access count
    bulk_api_user.refresh_from_db()

    # Check that the access count was incremented
    assert (
        bulk_api_user.access_count == initial_access_count + 1
    ), "Access count should be incremented"


def test_duck_database_is_valid(
    client: Client,
    bulk_api_user: BulkAPIUser,
    static_settings: tuple[Path, Path],
    tmp_path: Path,
):
    """Test that the downloaded file is a valid duckdb database"""

    # Make the request with a valid token to verify it works
    response = client.get(
        f"{reverse('duckdb_download')}?token={bulk_api_user.token}", follow=True
    )

    # The final response should have status code 200
    assert response.status_code == 200
    # Assert that the response is a FileResponse, confirming our overridden redirect was used
    assert isinstance(response, FileResponse), "Response should be a FileResponse"
    # Verify the Content-Disposition header to ensure proper file download parameters
    assert (
        response["Content-Disposition"] == 'attachment; filename="twfy_votes.duckdb"'
    ), "Content-Disposition header is incorrect"

    # extract streaming_content to a file
    db_file = tmp_path / "twfy_votes.duckdb"
    with open(db_file, "wb") as f:
        for chunk in response.streaming_content:  # type: ignore
            f.write(chunk)

    # Now try to connect to the test database file directly
    try:
        conn = duckdb.connect(str(db_file))
        result = conn.execute("SELECT * FROM test").fetchall()
        conn.close()

        # Verify the data
        assert len(result) == 1
        assert result[0][0] == 1
        assert result[0][1] == "test"
    except Exception as e:
        pytest.fail(f"Failed to connect to the duckdb database: {e}")
