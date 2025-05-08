import sys
import traceback

from django.core.mail import mail_admins
from django.core.management.base import BaseCommand

from votes.check_for_updates import check_for_external_update_markers
from votes.models import Update

from .populate import Command as PopulateCommand


class Command(BaseCommand):
    help = "Run update queue"
    message = "Uploading data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-for-updates", action="store_true", help="Silence progress bars."
        )

    def handle(
        self,
        check_for_updates: bool = False,
        *args,
        **options,
    ):
        if check_for_updates:
            check_for_external_update_markers()

        for update in Update.to_run():
            if not update.check_similar_in_progress():
                update.start()
                try:
                    PopulateCommand().handle(**update.instructions)
                    update.complete()
                except Exception as e:
                    # Get full traceback
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    tb_str = "".join(
                        traceback.format_exception(exc_type, exc_value, exc_traceback)
                    )

                    # Send email to admins
                    subject = f"Error in PopulateCommand for update {update.id}"
                    message = (
                        f"An error occurred while running PopulateCommand for update {update.id}:\n\n"
                        f"Instructions: {update.instructions}\n\n"
                        f"Error: {str(e)}\n\n"
                        f"Traceback:\n{tb_str}"
                    )

                    mail_admins(subject, message, fail_silently=False)

                    # Mark the update as failed
                    update.fail(str(e))

                    # Re-raise the exception to ensure command exits with error code
                    raise
