from pathlib import Path

from django.conf import settings

import rich
import tomllib

from ..models import GovernmentParty
from .register import import_register


@import_register.register("government_parties", group="basic", order=0)
def populate_government_parties(quiet: bool = False):
    BASE_DIR = Path(settings.BASE_DIR)

    data_file = BASE_DIR / "data" / "government_parties.toml"

    data = tomllib.loads(data_file.read_text())

    to_create = []

    for row in data["government"]:
        for party in row["party"]:
            for chamber in row["chamber"]:
                item = GovernmentParty(
                    label=row["label"],
                    chamber=chamber,
                    party=party,
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                )
                to_create.append(item)

    if not quiet:
        rich.print(
            f"Deleting [red]{GovernmentParty.objects.count()}[/red] existing records"
        )
    GovernmentParty.objects.all().delete()
    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] new records")
    GovernmentParty.objects.bulk_create(to_create)
