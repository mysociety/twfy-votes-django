from django.core.management import call_command

import pytest

from votes.models import Update
from votes.populate.register import ImportOrder, import_register

pytestmark = pytest.mark.django_db


class TestModelState:
    executed = False
    value = "initial_value"

    @classmethod
    def reset(cls):
        """Reset the test flags for fresh tests"""
        cls.executed = False
        cls.value = "initial_value"


test_model_state = TestModelState


@pytest.fixture(scope="module", autouse=True)
def register_test_model():
    """Register the test model in the import_register for the tests"""

    # Define the test model function
    @import_register.register("test_model", group=ImportOrder.USER_GROUPS)
    def import_test_model(quiet: bool = False):
        """
        Simple test model that just sets a flag.
        Used purely for testing the queue system.
        We don't try to pass a custom value parameter, as the current
        implementation of run_import only supports quiet and update_since.
        """
        test_model_state.executed = True

        # We'll use the presence of quiet=True to simulate our custom behavior
        # This way we can verify queue execution without requiring custom parameter passing
        if quiet:
            test_model_state.value = "completed_value"

        if not quiet:
            print("Test model executed")

    yield

    # Clean up after all tests - remove test_model from import_register
    if "test_model" in import_register.import_functions:
        del import_register.import_functions["test_model"]

    # Remove from the group
    if ImportOrder.USER_GROUPS in import_register.groups:
        if "test_model" in import_register.groups[ImportOrder.USER_GROUPS]:
            import_register.groups[ImportOrder.USER_GROUPS].remove("test_model")


class TestUpdateQueue:
    """Tests for the Update queue system"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Reset the state before each test"""
        test_model_state.reset()
        # Clean up any existing queue items
        Update.objects.all().delete()
        yield
        # Clean up after test
        Update.objects.all().delete()
        test_model_state.reset()

    def test_queue_execution(self):
        """Test that a task can be created and executed via the queue"""
        # Create a task with our test model
        instructions = {"model": "test_model", "value": "test_value", "quiet": True}

        # Verify initial state
        assert test_model_state.executed is False
        assert test_model_state.value == "initial_value"

        # Create the task
        task = Update.create_task(
            instructions=instructions,
            created_via="test_update_queue",
            check_for_running=True,
        )

        # Verify task was created
        assert task.id is not None
        assert task.instructions == instructions
        assert task.date_created is not None
        assert task.date_started is None
        assert task.date_completed is None
        assert task.failed is False

        # Run the queue
        call_command("run_queue")

        # Refresh the task from the database
        task.refresh_from_db()

        # Verify task was completed
        assert task.date_started is not None
        assert task.date_completed is not None
        assert task.failed is False

        # Verify the test model was executed
        assert test_model_state.executed is True
        assert test_model_state.value == "completed_value"

    def test_queue_deduplication(self):
        """Test that duplicate tasks are not created"""
        # Create the same task twice
        instructions = {"model": "test_model", "quiet": True}

        task1 = Update.create_task(
            instructions=instructions,
            created_via="test_update_queue",
            check_for_running=True,
        )

        task2 = Update.create_task(
            instructions=instructions,
            created_via="test_update_queue",
            check_for_running=True,
        )

        # Verify that only one task was created
        assert task1.id == task2.id
        assert Update.objects.count() == 1

    def test_failed_task(self):
        """Test handling of a failed task"""
        # Create a task that will fail (no such model)
        instructions = {"model": "nonexistent_model", "quiet": True}

        task = Update.create_task(
            instructions=instructions,
            created_via="test_update_queue",
            check_for_running=True,
        )

        # Run the queue, expect an exception but continue
        with pytest.raises(Exception):
            call_command("run_queue")

        # Refresh the task from the database
        task.refresh_from_db()

        # Verify task was started
        assert task.date_started is not None
        assert task.date_completed is not None
        assert task.failed is True
        assert task.error_message != ""
