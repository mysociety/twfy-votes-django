from pathlib import Path

from django.conf import settings

import rich
import tomllib

from ..models.decisions import Chamber, PolicyComparisonPeriod
from .register import ImportOrder, import_register


@import_register.register("comparison_periods", ImportOrder.LOOKUPS)
def populate_comparison_periods(quiet: bool = False):
    BASE_DIR = Path(settings.BASE_DIR)

    data_file = BASE_DIR / "data" / "lookups" / "comparison_periods.toml"

    data = tomllib.loads(data_file.read_text())

    chamber_ids_from_slug = Chamber.id_from_slug("slug")

    to_create = []

    for row in data["period"]:
        chamber = row["chamber_slug"]
        item = PolicyComparisonPeriod(
            slug=row["slug"],
            description=row["description"],
            chamber_slug=chamber,
            chamber_id=chamber_ids_from_slug[chamber],
            start_date=row["start_date"],
            end_date=row["end_date"],
        )
        to_create.append(item)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] comparison periods")

    lookup_manager = PolicyComparisonPeriod.get_lookup_manager("chamber_id", "slug")
    to_create = lookup_manager.add_ids(to_create)

    with PolicyComparisonPeriod.disable_constraints():
        PolicyComparisonPeriod.objects.all().delete()
        PolicyComparisonPeriod.objects.bulk_create(to_create, batch_size=1000)
