import json

import pytest

from votes.forms import BulkVoteAnnotationForm
from votes.models import Division, Person

pytestmark = pytest.mark.django_db


@pytest.fixture
def valid_division():
    """Get a valid division from the database for testing"""
    return Division.objects.first()


@pytest.fixture
def valid_person():
    """Get a valid person from the database for testing"""
    return Person.objects.first()


def test_bulk_vote_annotation_form_valid_person_ids(valid_division, valid_person):
    """Test that the form validates when all person IDs exist in the database"""
    form_data = {
        "decision_id": valid_division.id,
        "annotations_json": json.dumps(
            [
                {
                    "person_id": valid_person.id,
                    "link": "https://example.com/reference",
                    "detail": "Valid annotation",
                }
            ]
        ),
    }

    form = BulkVoteAnnotationForm(data=form_data)
    assert form.is_valid(), f"Form should be valid but got errors: {form.errors}"


def test_bulk_vote_annotation_form_invalid_person(valid_division):
    """Test that the form raises ValidationError for person IDs if invalid person id"""
    form_data = {
        "decision_id": valid_division.id,
        "annotations_json": json.dumps(
            [
                {
                    "person_id": 9999,  # Invalid person ID below 10000
                    "link": "https://example.com/reference",
                    "detail": "Invalid annotation",
                }
            ]
        ),
    }

    form = BulkVoteAnnotationForm(data=form_data)
    assert not form.is_valid(), "Form should be invalid for non-existent person ID"

    # Check that the error message mentions the invalid person ID
    assert "annotations_json" in form.errors
    error_message = str(form.errors["annotations_json"])
    assert "9999" in error_message
    assert "do not exist" in error_message


def test_bulk_vote_annotation_form_multiple_invalid_person_ids(valid_division):
    """Test that the form reports all invalid person IDs in the error message"""
    form_data = {
        "decision_id": valid_division.id,
        "annotations_json": json.dumps(
            [
                {
                    "person_id": 1,  # Invalid person ID
                    "link": "https://example.com/reference1",
                    "detail": "Invalid annotation 1",
                },
                {
                    "person_id": 2,  # Invalid person ID
                    "link": "https://example.com/reference2",
                    "detail": "Invalid annotation 2",
                },
            ]
        ),
    }

    form = BulkVoteAnnotationForm(data=form_data)
    assert not form.is_valid(), "Form should be invalid for non-existent person IDs"

    # Check that the error message mentions both invalid person IDs
    error_message = str(form.errors["annotations_json"])
    assert "1" in error_message
    assert "2" in error_message
    assert "do not exist" in error_message


def test_bulk_vote_annotation_form_mixed_valid_invalid_person_ids(
    valid_division, valid_person
):
    """Test that the form fails when mixing valid and invalid person IDs"""
    form_data = {
        "decision_id": valid_division.id,
        "annotations_json": json.dumps(
            [
                {
                    "person_id": valid_person.id,  # Valid person ID
                    "link": "https://example.com/reference1",
                    "detail": "Valid annotation",
                },
                {
                    "person_id": 9999,  # Invalid person ID
                    "link": "https://example.com/reference2",
                    "detail": "Invalid annotation",
                },
            ]
        ),
    }

    form = BulkVoteAnnotationForm(data=form_data)
    assert (
        not form.is_valid()
    ), "Form should be invalid when any person ID doesn't exist"

    # Check that only the invalid person ID is mentioned in the error
    error_message = str(form.errors["annotations_json"])
    assert "9999" in error_message
    assert str(valid_person.id) not in error_message
    assert "do not exist" in error_message


def test_bulk_vote_annotation_form_delete_with_invalid_person_id(valid_division):
    """Test that delete operations also validate person IDs"""
    form_data = {
        "decision_id": valid_division.id,
        "annotations_json": json.dumps(
            [{"person_id": 9999, "delete": True}]  # Invalid person ID
        ),
    }

    form = BulkVoteAnnotationForm(data=form_data)
    assert (
        not form.is_valid()
    ), "Form should be invalid even for delete operations with non-existent person ID"

    error_message = str(form.errors["annotations_json"])
    assert "9999" in error_message
    assert "do not exist" in error_message


def test_bulk_vote_annotation_form_empty_person_ids_list(valid_division):
    """Test that empty annotations list is handled gracefully"""
    form_data = {"decision_id": valid_division.id, "annotations_json": json.dumps([])}

    form = BulkVoteAnnotationForm(data=form_data)
    # Empty list should be valid (no person IDs to validate)
    assert (
        form.is_valid()
    ), f"Form should be valid for empty list but got errors: {form.errors}"


def test_bulk_vote_annotation_form_invalid_json():
    """Test that invalid JSON is handled with a proper error message"""
    form_data = {
        "decision_id": 1,
        "annotations_json": '{"invalid": json}',  # Invalid JSON
    }

    form = BulkVoteAnnotationForm(data=form_data)
    assert not form.is_valid(), "Form should be invalid for malformed JSON"

    error_message = str(form.errors["annotations_json"])
    assert "Invalid JSON format" in error_message
