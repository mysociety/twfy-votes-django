from django.core.management import call_command

import pytest


@pytest.mark.django_db
def test_for_unapplied_model_changes():
    """
    Test to check if there are model changes in the 'votes' app that are not reflected in migrations.
    """
    # Run the makemigrations command with the check flag
    call_command("makemigrations", "votes", check=True, dry_run=True)
