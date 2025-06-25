"""
Name reconciliation utilities for handling person IDs in legislative data.
"""

import datetime
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from mysoc_validator import Popolo
from mysoc_validator.models.popolo import Chamber

DATA_DIR = Path(__file__).parent.parent / "data" / "source"


@lru_cache
def get_popolo():
    return Popolo.from_path(DATA_DIR / "people.json")


def extract_person_id_from_brackets(full_name: str) -> Optional[int]:
    """
    Extract person ID from a name that has it in brackets.

    Args:
        full_name: The full name potentially containing person ID in brackets

    Returns:
        The person ID if found in brackets, None otherwise

    Examples:
        'Diane Abbott (10001)' -> 10001
        'John Smith' -> None
    """
    # Look for pattern like (12345) at the end of the name
    match = re.search(r"\((\d+)\)$", full_name.strip())
    if match:
        return int(match.group(1))
    return None


def strip_honorifics(full_name: str) -> str:
    """
    Remove common honorifics from a person's name.

    Args:
        full_name: The full name potentially containing honorifics

    Returns:
        The name with honorifics removed
    """
    # List of common pre-honorifics to remove (at the beginning)
    pre_honorifics = [
        r"\bDame\b",
        r"\bSir\b",
        r"\bMr\b",
        r"\bMrs\b",
        r"\bMs\b",
        r"\bMiss\b",
        r"\bDr\b",
        r"\bProf\b",
        r"\bProfessor\b",
        r"\bRev\b",
        r"\bReverend\b",
        r"\bLord\b",
        r"\bLady\b",
        r"\bHon\b",
        r"\bHonourable\b",
        r"\bRt Hon\b",
        r"\bRight Hon\b",
        r"\bRight Honourable\b",
    ]

    # List of common post-honorifics to remove (at the end)
    post_honorifics = [
        r"\bMP\b",
        r"\bMSP\b",
        r"\bMLA\b",
        r"\bAM\b",
        r"\bMS\b",
        r"\bOBE\b",
        r"\bMBE\b",
        r"\bCBE\b",
        r"\bKBE\b",
        r"\bDBE\b",
        r"\bQC\b",
        r"\bKC\b",
        r"\bPC\b",
    ]

    # Remove pre-honorifics (case insensitive)
    cleaned_name = full_name
    for honorific in pre_honorifics:
        cleaned_name = re.sub(honorific, "", cleaned_name, flags=re.IGNORECASE)

    # Remove post-honorifics (case insensitive)
    for honorific in post_honorifics:
        cleaned_name = re.sub(honorific, "", cleaned_name, flags=re.IGNORECASE)

    # Clean up extra whitespace
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()

    return cleaned_name


def person_id_from_name(
    full_name: str, chamber_slug: str, date: datetime.date
) -> Optional[int]:
    """
    Find a person ID from their name, with fallback strategies for manual reconciliation.

    Args:
        full_name: The full name of the person
        chamber_slug: The chamber identifier
        date: The date for the lookup

    Returns:
        The person ID if found, None otherwise
    """
    # First check if there's a manual ID in brackets (e.g., "Diane Abbott (10001)")
    manual_id = extract_person_id_from_brackets(full_name)
    if manual_id is not None:
        return manual_id

    chamber = Chamber(chamber_slug)
    popolo = get_popolo()

    # Try with the original name
    person = popolo.persons.from_name(full_name, chamber_id=chamber, date=date)

    # If not found, try with honorifics stripped
    if person is None:
        cleaned_name = strip_honorifics(full_name)
        person = popolo.persons.from_name(cleaned_name, chamber_id=chamber, date=date)

    if person is None:
        return None
    else:
        return int(person.reduced_id())
