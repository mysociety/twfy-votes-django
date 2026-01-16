"""
Tests for motion_types.yaml file
"""

import pytest

from votes.consts import MotionType
from votes.models import MotionTypeDescriptionCollection


@pytest.fixture
def motion_types_collection():
    """
    Load and return the motion types collection.
    """
    return MotionTypeDescriptionCollection.load()


def test_no_duplicate_chamber_combinations(
    motion_types_collection: MotionTypeDescriptionCollection,
):
    """
    Test no duplicate motion type + chamber combinations.
    """
    seen_combinations = set()

    for motion_type, motion_descriptions in motion_types_collection.root.items():
        for description in motion_descriptions:
            combination = (motion_type, description.chamber)
            assert (
                combination not in seen_combinations
            ), f"Duplicate found: motion_type='{motion_type}', chamber='{description.chamber}'"
            seen_combinations.add(combination)


def test_all_motion_types_have_all_chamber(
    motion_types_collection: MotionTypeDescriptionCollection,
):
    """
    Test that every motion type has an 'all' chamber entry.
    """
    for motion_type, motion_descriptions in motion_types_collection.root.items():
        chambers = [desc.chamber for desc in motion_descriptions]
        assert (
            "all" in chambers
        ), f"Motion type '{motion_type}' should have an 'all' chamber entry. Found: {chambers}"


def test_all_enum_values_present(
    motion_types_collection: MotionTypeDescriptionCollection,
):
    """
    Test that all MotionType enum values are present.
    """
    collection_keys = set(motion_types_collection.root.keys())
    enum_values = set(MotionType)

    missing = enum_values - collection_keys
    assert not missing, f"Missing MotionType values: {sorted(missing)}"


def test_collection_methods_work_correctly(
    motion_types_collection: MotionTypeDescriptionCollection,
):
    """
    Test that the collection methods return expected values.
    """
    # Test with a known motion type that should exist
    motion_type = MotionType.AMENDMENT

    # Test get_title and get_description for 'all' chamber
    title = motion_types_collection.get_title(motion_type, "all")
    description = motion_types_collection.get_description(motion_type, "all")

    assert title != "Unknown Motion Type", f"Should have a title for {motion_type}"
    assert (
        description != "No description available."
    ), f"Should have a description for {motion_type}"

    # Test that fallback to 'all' works for specific chambers
    title_specific = motion_types_collection.get_title(motion_type, "commons")
    description_specific = motion_types_collection.get_description(
        motion_type, "commons"
    )

    # Should return valid values (either specific or fallback to 'all')
    assert title_specific != "Unknown Motion Type"
    assert description_specific != "No description available."
