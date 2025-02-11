from pathlib import Path

from django.conf import settings

import rich
import tomllib

from ..models import Chamber, GovernmentParty
from .register import ImportOrder, import_register


@import_register.register("government_parties", ImportOrder.LOOKUPS)
def populate_government_parties(quiet: bool = False):
    BASE_DIR = Path(settings.BASE_DIR)

    data_file = BASE_DIR / "data" / "lookups" / "government_parties.toml"

    data = tomllib.loads(data_file.read_text())

    chamber_ids_from_slug = Chamber.id_from_slug("slug")

    to_create = []

    for row in data["government"]:
        for party in row["party"]:
            for chamber in row["chamber"]:
                item = GovernmentParty(
                    label=row["label"],
                    chamber_slug=chamber,
                    chamber_id=chamber_ids_from_slug[chamber],
                    party=party,
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                )
                to_create.append(item)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] government parties")

    lookup_manager = GovernmentParty.get_lookup_manager(
        "chamber_id", "party", "start_date", "end_date"
    )
    to_create = lookup_manager.add_ids(to_create)

    GovernmentParty.objects.all().delete()
    GovernmentParty.objects.bulk_create(to_create, batch_size=1000)
