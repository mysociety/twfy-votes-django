import pytest

pytestmark = pytest.mark.django_db


def test_fast_slow():
    from votes.management.commands.vr_validator import test_policy_sample

    has_errors = test_policy_sample(sample=20)

    if has_errors:
        raise ValueError("Errors found in policy generation")
