from datetime import date, timedelta

from django.core.management.base import BaseCommand

from votes.populate import import_register


class Command(BaseCommand):
    help = "Upload data"
    message = "Uploading data"

    def add_arguments(self, parser):
        parser.add_argument(
            "-q", "--quiet", action="store_true", help="Silence progress bars."
        )

        parser.add_argument(
            "--model", type=str, help="Run a single model", nargs="?", const=""
        )

        parser.add_argument(
            "--group", type=str, help="Run a group of models", nargs="?", const=""
        )

        parser.add_argument(
            "--start-group", type=str, help="Run a group of models", nargs="?", const=""
        )

        parser.add_argument(
            "--end-group", type=str, help="Run a group of models", nargs="?", const=""
        )

        parser.add_argument(
            "--update-since",
            type=date.fromisoformat,
            help="Update since a certain date",
            default=None,
        )
        parser.add_argument(
            "--update-last",
            type=int,
            help="Update last x days",
            default=None,
        )
        parser.add_argument("--all", action="store_true", help="Run all models")

    def handle(
        self,
        *args,
        model: str = "",
        group: str = "",
        start_group: str = "",
        end_group: str = "",
        all: bool = False,
        quiet: bool = False,
        update_since: date | None = None,
        update_last: int | None = None,
        **options,
    ):
        if group and (start_group or end_group):
            self.stdout.write("You cannot specify both group and start/end group")
            return
        if start_group and not end_group:
            self.stdout.write("You must specify both start-group and end-group")
            return
        if update_last and update_since:
            self.stdout.write("You cannot specify both update-last and update-since")
            return

        if update_last:
            update_since = date.today() - timedelta(days=update_last)

        if not quiet and update_since:
            print(f"Updating since {update_since}")
        if model:
            import_register.run_import(model, quiet, update_since)
        elif group:
            import_register.run_group(group, quiet, update_since)
        elif start_group:
            import_register.run_group_range(start_group, end_group, quiet, update_since)
        elif all:
            import_register.run_all(quiet, update_since)
        else:
            self.stdout.write("You must specify a model, group or all")
            return
