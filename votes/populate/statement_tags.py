import datetime
from pathlib import Path

from django.conf import settings

from twfy_votes.helpers.duck import DuckQuery

from ..consts import ChamberSlug
from ..models import DecisionTag, Statement, StatementTagLink
from .register import ImportOrder, import_register

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


@import_register.register("statement_tags", group=ImportOrder.DIVISION_ANALYSIS)
def import_divisions(quiet: bool = False, update_since: datetime.date | None = None):
    add_prayers_tag(quiet=quiet)
