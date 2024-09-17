from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from django.conf import settings
from django.db import connection

from twfy_votes.helpers.duck import sync_to_postgres
from twfy_votes.helpers.typed_django.models import ModelType, TypedModel


@contextmanager
def disable_constraints(table_name: str):
    """
    Postgres specific context manager to disable foreign key constraints.

    We do this because we're generally importing whole database tables from elsewhere.
    So by definition, we can preserve foreign key relationships.

    We don't want to get into complicated checks of differences between tables, just dump,
    reimport and then re-enable constraints.
    """
    try:
        # Disable foreign key constraints
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {table_name} DISABLE TRIGGER ALL;")

        # Yield control back to the caller
        yield
    finally:
        # Re-enable foreign key constraints
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {table_name} ENABLE TRIGGER ALL;")


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
    def disable_constraints(cls):
        """
        Postgres specific context manager to disable foreign key constraints.

        We do this because we're generally importing whole database tables from elsewhere.
        So by definition, we can preserve foreign key relationships.

        We don't want to get into complicated checks of differences between tables, just dump,
        reimport and then re-enable constraints.
        """
        return disable_constraints(cls._meta.db_table)

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
