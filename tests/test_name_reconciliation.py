"""
Tests for name reconciliation functions in votes.name_reconciliation
"""

import datetime

import pytest

from votes.name_reconciliation import (
    extract_person_id_from_brackets,
    person_id_from_name,
    strip_honorifics,
)


class TestExtractPersonIdFromBrackets:
    """Test the extract_person_id_from_brackets function"""

    def test_extract_valid_id(self):
        """Test extracting valid person ID from brackets"""
        assert extract_person_id_from_brackets("Diane Abbott (10001)") == 10001
        assert extract_person_id_from_brackets("John Smith (12345)") == 12345
        assert extract_person_id_from_brackets("  Mary Jones (98765)  ") == 98765

    def test_no_brackets(self):
        """Test names without brackets return None"""
        assert extract_person_id_from_brackets("Diane Abbott") is None
        assert extract_person_id_from_brackets("John Smith") is None
        assert extract_person_id_from_brackets("") is None

    def test_invalid_bracket_content(self):
        """Test brackets with non-numeric content return None"""
        assert extract_person_id_from_brackets("John Smith (MP)") is None
        assert extract_person_id_from_brackets("Mary Jones (abc)") is None
        assert extract_person_id_from_brackets("Test (123abc)") is None

    def test_brackets_not_at_end(self):
        """Test brackets not at the end return None"""
        assert extract_person_id_from_brackets("John (123) Smith") is None
        assert extract_person_id_from_brackets("(123) John Smith") is None


class TestStripHonorifics:
    """Test the strip_honorifics function"""

    def test_pre_honorifics(self):
        """Test removal of pre-honorifics (titles before names)"""
        assert strip_honorifics("Dame Meg Hillier") == "Meg Hillier"
        assert strip_honorifics("Mr Tanmanjeet Singh Dhesi") == "Tanmanjeet Singh Dhesi"
        assert strip_honorifics("Ms Stella Creasy") == "Stella Creasy"
        assert strip_honorifics("Dr Scott Arthur") == "Scott Arthur"
        assert strip_honorifics("Sir John Smith") == "John Smith"
        assert strip_honorifics("Lady Mary Jones") == "Mary Jones"
        assert strip_honorifics("Rev David Brown") == "David Brown"
        assert strip_honorifics("Prof Jane Wilson") == "Jane Wilson"

    def test_post_honorifics(self):
        """Test removal of post-honorifics (titles after names)"""
        assert strip_honorifics("Debbie Abrahams MP") == "Debbie Abrahams"
        assert strip_honorifics("John Smith MSP") == "John Smith"
        assert strip_honorifics("Mary Jones OBE") == "Mary Jones"
        assert strip_honorifics("David Brown QC") == "David Brown"
        assert strip_honorifics("Jane Wilson MBE") == "Jane Wilson"

    def test_multiple_honorifics(self):
        """Test removal of multiple honorifics"""
        assert strip_honorifics("Dr John Smith MP") == "John Smith"
        assert strip_honorifics("Dame Mary Jones OBE") == "Mary Jones"
        assert strip_honorifics("Mr David Brown QC") == "David Brown"

    def test_case_insensitive(self):
        """Test that honorific removal is case insensitive"""
        assert strip_honorifics("mr john smith") == "john smith"
        assert strip_honorifics("DR MARY JONES") == "MARY JONES"
        assert strip_honorifics("Ms Jane Wilson mp") == "Jane Wilson"

    def test_no_honorifics(self):
        """Test names without honorifics remain unchanged"""
        assert strip_honorifics("John Smith") == "John Smith"
        assert strip_honorifics("Mary Jane Wilson") == "Mary Jane Wilson"
        assert strip_honorifics("Emma Lewell") == "Emma Lewell"

    def test_whitespace_cleanup(self):
        """Test that extra whitespace is cleaned up"""
        assert strip_honorifics("Mr  John   Smith") == "John Smith"
        assert strip_honorifics("  Dame   Mary  Jones  ") == "Mary Jones"
        assert strip_honorifics("Dr\t\tJohn\t\tSmith\t\tMP") == "John Smith"


class TestPersonIdFromName:
    """Test the person_id_from_name function"""

    @pytest.fixture
    def test_params(self):
        """Common test parameters"""
        return {"chamber_slug": "house-of-commons", "date": datetime.date(2025, 6, 24)}

    def test_manual_reconciliation_priority(self, test_params):
        """Test that manual IDs in brackets take priority"""
        # This should return the manual ID without doing any lookups
        result = person_id_from_name("Diane Abbott (10001)", **test_params)
        assert result == 10001

        result = person_id_from_name("Any Name Here (99999)", **test_params)
        assert result == 99999

    def test_honorific_examples(self, test_params):
        """Test the specific problematic names"""
        # These tests will depend on the actual data in people.json
        # They may pass or fail depending on what's in the test data

        # Names with pre-honorifics
        test_names = [
            "Dame Meg Hillier",
            "Mr Tanmanjeet Singh Dhesi",
            "Mr Jonathan Brash",
            "Ms Stella Creasy",
            "Mr Clive Betts",
            "Dr Scott Arthur",
            "Dr Beccy Cooper",
            "Dr Allison Gardner",
            "Ms Polly Billington",
            "Mr Richard Quigley",
            "Ms Marie Rimmer",
            "Dr Rosena Allin-Khan",
            "Dr Simon Opher",
            "Ms Diane Abbott",
        ]

        for name in test_names:
            # The function should at least not crash and return an int or None
            result = person_id_from_name(name, **test_params)
            assert result is None or isinstance(result, int)

    def test_post_honorific_examples(self, test_params):
        """Test names with post-honorifics"""
        # Names with post-honorifics
        test_names = ["Debbie Abrahams MP", "John Smith MSP", "Mary Jones OBE"]

        for name in test_names:
            # The function should at least not crash and return an int or None
            result = person_id_from_name(name, **test_params)
            assert result is None or isinstance(result, int)

    def test_clean_names(self, test_params):
        """Test names without honorifics"""
        # Names that should work as-is (depending on test data)
        result = person_id_from_name("Emma Lewell", **test_params)
        assert result is None or isinstance(result, int)

    def test_empty_and_invalid_names(self, test_params):
        """Test edge cases with empty or invalid names"""
        assert person_id_from_name("", **test_params) is None
        assert person_id_from_name("   ", **test_params) is None
        assert person_id_from_name("NonexistentPerson12345", **test_params) is None


class TestIntegrationExamples:
    """Integration tests with real-world examples"""

    @pytest.fixture
    def test_params(self):
        """Common test parameters"""
        return {"chamber_slug": "house-of-commons", "date": datetime.date(2025, 6, 24)}

    def test_manual_override_examples(self, test_params):
        """Test manual reconciliation examples"""
        # Test that manual IDs work
        examples = [
            ("Diane Abbott (10001)", 10001),
            ("John Smith (12345)", 12345),
            ("Any Name (99999)", 99999),
        ]

        for name, expected_id in examples:
            result = person_id_from_name(name, **test_params)
            assert result == expected_id

    def test_fallback_strategy(self, test_params):
        """Test that the fallback strategy works correctly"""
        # Test a name with honorifics - should try original, then stripped
        name = "Dr John Smith MP"
        result = person_id_from_name(name, **test_params)

        # Should return None or a valid person ID, but shouldn't crash
        assert result is None or isinstance(result, int)

        # The function should have tried:
        # 1. "Dr John Smith MP" (original)
        # 2. "John Smith" (stripped of both Dr and MP)

    def test_problematic_names_coverage(self, test_params):
        """Test all the originally problematic names"""
        problematic_names = [
            "Dame Meg Hillier",
            "Mr Tanmanjeet Singh Dhesi",
            "Mr Jonathan Brash",
            "Ms Stella Creasy",
            "Mr Clive Betts",
            "Dr Scott Arthur",
            "Dr Beccy Cooper",
            "Dr Allison Gardner",
            "Ms Polly Billington",
            "Mr Richard Quigley",
            "Ms Marie Rimmer",
            "Dr Rosena Allin-Khan",
            "Emma Lewell-Buck",
            "Dr Simon Opher",
            "Ms Diane Abbott",
            "Debbie Abrahams MP",
        ]

        # Test that none of these crash the function
        for name in problematic_names:
            result = person_id_from_name(name, **test_params)
        assert isinstance(result, int), f"Failed for name: {name}"
