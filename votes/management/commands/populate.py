from datetime import date, timedelta

from django.core.management.base import BaseCommand

from rich.console import Console
from rich.table import Table

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
    "refresh_policies": {
        "update_last": 7,
        "start_group": "policies",
        "end_group": "policycalc",
    },
}


class Command(BaseCommand):
    help = "Upload data by running specific models or groups (see --show-options for details)"
    message = "Uploading data"

    def print_help_table(self):
        """Print a rich table showing all available groups and models"""
        console = Console()

        # Create table for shortcuts
        shortcuts_table = Table(title="Available Shortcuts", border_style="blue")
        shortcuts_table.add_column("Shortcut", style="cyan")
        shortcuts_table.add_column("Description", style="green")

        for shortcut_name, details in shortcuts.items():
            description_parts = []
            update_last = details.get("update_last")
            if update_last is not None:
                description_parts.append(f"Last {update_last} days")

            start_group = details.get("start_group")
            end_group = details.get("end_group")
            if start_group and end_group:
                description_parts.append(f"Groups {start_group} to {end_group}")

            if details.get("all", False):
                description_parts.append("All models")

            shortcuts_table.add_row(shortcut_name, ", ".join(description_parts))

        # Create table for groups and models
        groups_table = Table(title="Available Groups and Models", border_style="blue")
        groups_table.add_column("Group", style="cyan")
        groups_table.add_column("Order", style="magenta")
        groups_table.add_column("Model", style="green")

        # Sort groups by their enum value
        groups = []
        for group_enum, model_list in import_register.groups.items():
            groups.append((group_enum, model_list))
        groups.sort(key=lambda x: x[0].value)

        for group_enum, model_list in groups:
            # Add each model on its own row
            for model in model_list:
                groups_table.add_row(
                    group_enum.name.lower(), str(group_enum.value), model
                )

        console.print(shortcuts_table)
        console.print("\n")
        console.print(groups_table)

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
            "--start-group",
            type=str,
            help="Run a group of models and all following groups up to end-group",
            nargs="?",
            const="",
        )

        parser.add_argument(
            "--end-group",
            type=str,
            help="End group for range of models to run",
            nargs="?",
            const="",
        )

        parser.add_argument(
            "--shortcut",
            type=str,
            help="Run a group of models using a predefined configuration",
            nargs="?",
            const="",
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

        parser.add_argument(
            "--show-options",
            action="store_true",
            help="Show tables of available groups and models",
        )

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
        show_options: bool = False,
        **options,
    ):
        # If show_options is True, just show the tables and exit
        if show_options:
            self.print_help_table()
            return

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
