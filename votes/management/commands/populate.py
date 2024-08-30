from django.core.management.base import BaseCommand

from votes.populate import import_register


class Command(BaseCommand):
    help = "Upload data"
    message = "Uploading data"

    def add_arguments(self, parser):
        parser.add_argument(
            "-q", "--quiet", action="store_true", help="Silence progress bars."
        )

        # I need three options here
        # an --model level an --group level and an --all level

        # I need to be able to run a single model, a group of models or all models

        parser.add_argument(
            "--model", type=str, help="Run a single model", nargs="?", const=""
        )

        parser.add_argument(
            "--group", type=str, help="Run a group of models", nargs="?", const=""
        )

        parser.add_argument("--all", action="store_true", help="Run all models")

    def handle(
        self,
        *args,
        model: str = "",
        group: str = "",
        all: bool = False,
        quiet: bool = False,
        **options,
    ):
        if model:
            import_register.run_import(model, quiet)
        elif group:
            import_register.run_group(group, quiet)
        elif all:
            import_register.run_all(quiet)
        else:
            self.stdout.write("You must specify a model, group or all")
            return
