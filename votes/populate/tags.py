from __future__ import annotations

import datetime
from pathlib import Path

from django.conf import settings

import rich
from pydantic import BaseModel, TypeAdapter
from ruamel.yaml import YAML

from ..consts import TagType
from ..models import DecisionTag
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
lookup_dir = Path(BASE_DIR, "data", "lookups")
tags_path = lookup_dir / "tags.yaml"


class PartialTag(BaseModel):
    slug: str
    name: str
    description: str
    tag_type: TagType

    @property
    def key(self) -> tuple[str, str]:
        return (self.tag_type, self.slug)


PartialTagList = TypeAdapter(list[PartialTag])


@import_register.register("tags", group=ImportOrder.PRE_DIVISION_ANALYSIS)
def import_tags(quiet: bool = False, update_since: datetime.date | None = None):
    """
    Import tags from the YAML file.
    """
    if not quiet:
        rich.print("[blue]Importing tags[/blue]")

    yaml = YAML(typ="safe")  # default, if not specfied, is 'rt' (round-trip)

    data = yaml.load(tags_path)
    tags = PartialTagList.validate_python(data)

    lookup = DecisionTag.id_from_slugs("tag_type", "slug")

    to_create = []
    to_update = []

    for tag in tags:
        if tag.key not in lookup:
            to_create.append(
                DecisionTag(
                    slug=tag.slug,
                    name=tag.name,
                    desc=tag.description,
                    tag_type=tag.tag_type,
                )
            )
        else:
            to_update.append(
                DecisionTag(
                    id=lookup[tag.key],
                    slug=tag.slug,
                    name=tag.name,
                    desc=tag.description,
                    tag_type=tag.tag_type,
                )
            )

    if not quiet:
        rich.print(f"[blue]Creating {len(to_create)} tags[/blue]")
        rich.print(f"[blue]Updating {len(to_update)} tags[/blue]")

    if to_create:
        DecisionTag.objects.bulk_create(to_create, batch_size=1000)
    if to_update:
        DecisionTag.objects.bulk_update(to_update, ["name", "desc"], batch_size=1000)
