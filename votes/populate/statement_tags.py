import datetime
from pathlib import Path

from django.conf import settings

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug
from ..models import DecisionTag, Statement, StatementTagLink
from .register import ImportOrder, import_register
from .statements import load_statement_overrides

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])

BASE_DIR = Path(settings.BASE_DIR)
DATA_DIR = BASE_DIR / "data" / "source"


def add_prayers_tag(quiet: bool = False):
    prayers = list(
        Statement.objects.filter(
            extra_info__has_key="statutory_instrument_title",
            chamber_slug=ChamberSlug.COMMONS,
        ).values_list("id", flat=True)
    )

    tag = DecisionTag.objects.get(slug="objection_to_si")

    StatementTagLink.sync_tag_from_statement_id_list(
        tag, prayers, quiet=quiet, clear_absent=True
    )


def apply_override_tags(quiet: bool = False):
    """
    Apply tags from YAML overrides to their corresponding statements.
    Respects the tags specified in each override entry.
    """
    overrides = load_statement_overrides()

    # Build a mapping of tag_slug -> statement ids that should have that tag
    tag_statement_map = {}

    for override_key, override in overrides.items():
        # Find the statement
        stmt = Statement.objects.filter(
            original_id=override_key.original_id, chamber_slug=override_key.chamber
        ).first()

        if not stmt:
            continue

        # Add this statement to each tag specified in the override
        for tag_slug in override.tags:
            if tag_slug not in tag_statement_map:
                tag_statement_map[tag_slug] = []
            tag_statement_map[tag_slug].append(stmt.id)

    # Apply each tag to its statements
    for tag_slug, statement_ids in tag_statement_map.items():
        try:
            tag = DecisionTag.objects.get(slug=tag_slug)
            StatementTagLink.sync_tag_from_statement_id_list(
                tag, statement_ids, quiet=quiet, clear_absent=True
            )
        except DecisionTag.DoesNotExist:
            if not quiet:
                from rich import print as rprint

                rprint(f"[yellow]Warning: tag '{tag_slug}' not found[/yellow]")


@import_register.register("statement_tags", group=ImportOrder.DIVISION_ANALYSIS)
def import_divisions(quiet: bool = False, update_since: datetime.date | None = None):
    add_prayers_tag(quiet=quiet)
    apply_override_tags(quiet=quiet)
