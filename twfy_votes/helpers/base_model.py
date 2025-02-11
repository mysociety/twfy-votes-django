from dataclasses import dataclass
from pathlib import Path
from typing import Self

from django.conf import settings

from .duck import sync_to_postgres
from .typed_django.models import ModelType, TypedModel


@dataclass
class LookupManager:
    slug_fields: list[str]
    lookup_dict: dict[tuple[str, ...], int]

    def add_ids(self, items: list[ModelType]) -> list[ModelType]:
        for item in items:
            slug = tuple([getattr(item, field) for field in self.slug_fields])
            item.id = self.lookup_dict.get(slug, None)  # type: ignore
        return items


class DjangoVoteModel(TypedModel, abstract=True):
    def __str__(self):
        keys_to_try = ["slug", "key", "id"]
        for key in keys_to_try:
            if hasattr(self, key):
                return f"{self.__class__.__name__}({getattr(self, key)})"
        return super().__str__()

    @classmethod
    def id_from_slug(cls, slug_field: str) -> dict[str, int]:
        """
        Get a dictionary of ids from a slug field
        """
        return dict(cls.objects.values_list(slug_field, "id"))

    @classmethod
    def id_from_slugs(cls, *slug_fields: str) -> dict[tuple[str, ...], int]:
        """
        Get a dictionary of ids from a slug field
        """
        rows = cls.objects.values_list("id", *slug_fields)
        # we need to convert this [(1, "a", "b"), (2, "c", "d")] to
        # {("a", "b"): 1, ("c", "d"): 2}
        id_list: list[tuple[tuple[str, ...], int]] = []
        for row in rows:
            id_list.append((tuple(row[1:]), row[0]))
        return dict(id_list)

    @classmethod
    def get_lookup_manager(cls, *slug_fields: str):
        return LookupManager(list(slug_fields), cls.id_from_slugs(*slug_fields))

    @classmethod
    def maintain_existing_ids(cls, items: list[Self], *, slug_field: str) -> list[Self]:
        """
        If an item has an id, and the id is in the existing ids,
        keep the id. If the id is not in the existing ids, set to None.
        """
        existing_ids = cls.id_from_slug(slug_field)
        for item in items:
            item.id = existing_ids.get(getattr(item, slug_field), None)
        return items

    @classmethod
    def replace_with_parquet(cls, path: Path) -> int:
        """
        This empties the database and replaces it with the content of the parquet file.
        There are basic tests done for column alignment.
        """
        return sync_to_postgres(path, cls._meta.db_table, settings.DATABASES["default"])
