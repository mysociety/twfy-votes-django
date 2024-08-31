from pathlib import Path

from django.conf import settings

import rich
from ruamel.yaml import YAML

from ..consts import ChamberSlug
from ..models.decisions import Agreement, Chamber
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)


def add_ellipsis(text: str, max_length: int = 255) -> str:
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


@import_register.register("agreements", group=ImportOrder.DECISIONS)
def import_agreements(quiet: bool = False):
    yaml = YAML(typ="safe")

    agreements_file = BASE_DIR / "data" / "lookups" / "agreements.yaml"

    chamber_ids = Chamber.id_from_slug("slug")

    data = yaml.load(agreements_file.read_text())

    to_create = []
    for row in data:
        item = Agreement(
            key=f"a-{row['chamber_slug']}-{row['date']}-{row['decision_ref']}",
            chamber_slug=ChamberSlug(row["chamber_slug"]),
            chamber_id=chamber_ids[row["chamber_slug"]],
            date=row["date"],
            decision_ref=row["decision_ref"],
            decision_name=row["division_name"],
        )
        to_create.append(item)

    to_create = Agreement.get_lookup_manager("key").add_ids(to_create)

    with Agreement.disable_constraints():
        Agreement.objects.all().delete()
        Agreement.objects.bulk_create(to_create, batch_size=1000)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] agreements")
