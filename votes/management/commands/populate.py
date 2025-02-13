from datetime import date, timedelta

from django.core.management.base import BaseCommand

from votes.models import InstructionDict
from votes.populate import import_register

shortcuts: dict[str, InstructionDict] = {
    "refresh_commons_api": {
        "update_last": 1,
        "start_group": "api_votes",
        "end_group": "person_stats",
    },
    "refresh_motions_agreements": {
        "update_last": 3,
        "start_group": "download_motions",
        "end_group": "decisions",
    },
    "refresh_daily": {
        "update_last": 1,
        "all": True,
    },
    "refresh_recent": {
        "update_last": 10,
        "all": True,
    },
}


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
            "--shortcut", type=str, help="Run a group of models", nargs="?", const=""
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
        shortcut: str = "",
        all: bool = False,
        quiet: bool = False,
        update_since: date | None = None,
        update_last: int | None = None,
        **options,
    ):
        if shortcut:
            # use a stored set of instructions
            try:
                instructions = shortcuts[shortcut]
            except KeyError:
                self.stdout.write(f"Shortcut {shortcut} not found")
                return

            # shortcut should be the base, and then update if specified

            model = model or instructions.get("model", "")
            group = group or instructions.get("group", "")
            start_group = start_group or instructions.get("start_group", "")
            end_group = end_group or instructions.get("end_group", "")
            all = all or instructions.get("all", False)
            quiet = quiet or instructions.get("quiet", False)
            update_since = update_since or instructions.get("update_since", None)
            update_last = update_last or instructions.get("update_last", None)

        if group and (start_group or end_group):
            self.stdout.write("You cannot specify both group and start/end group")
            return
        if start_group and not end_group:
            self.stdout.write("You must specify both start-group and end-group")
            return
        if update_last is not None and update_since:
            self.stdout.write("You cannot specify both update-last and update-since")
            return

        if update_last is not None:
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
