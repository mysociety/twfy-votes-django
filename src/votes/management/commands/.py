from django.core.management.base import BaseCommand

from votes.check_for_updates import check_for_external_update_markers
from votes.models import Update

from .populate import Command as PopulateCommand


class Command(BaseCommand):
    help = "Run update queue"
    message = "Running update queue"

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
                PopulateCommand().handle(**update.instructions)
                update.complete()
