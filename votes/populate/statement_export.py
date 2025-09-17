import datetime
import json
from pathlib import Path

from django.conf import settings

import pandas as pd

from ..models import (
    Signature,
    Statement,
    StatementTagLink,
)
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
STATIC_DIR = Path(settings.STATIC_ROOT)
DATA_DIR = STATIC_DIR / "data"


def dump_statement_models(quiet: bool = False):
    """
    Export statement-related models to Parquet files
    """
    if not quiet:
        print("Dumping statement models to Parquet files")

    # Export Statements
    all_statements = pd.DataFrame(list(Statement.objects.all().values()))
    if len(all_statements) > 0:
        if "extra_data" in all_statements.columns:
            all_statements["extra_data"] = all_statements["extra_data"].apply(
                json.dumps
            )
        all_statements.to_parquet(DATA_DIR / "statements.parquet")

    # Export Signatures
    all_signatures = pd.DataFrame(list(Signature.objects.all().values()))
    if len(all_signatures) > 0:
        if "extra_data" in all_signatures.columns:
            all_signatures["extra_data"] = all_signatures["extra_data"].apply(
                json.dumps
            )
        all_signatures = all_signatures.drop(columns=["key"])
        all_signatures.to_parquet(DATA_DIR / "signatures.parquet")

    # Export StatementTagLinks
    all_statement_tag_links = pd.DataFrame(
        list(StatementTagLink.objects.all().values())
    )
    if len(all_statement_tag_links) > 0:
        if "extra_data" in all_statement_tag_links.columns:
            all_statement_tag_links["extra_data"] = all_statement_tag_links[
                "extra_data"
            ].apply(json.dumps)
        all_statement_tag_links.to_parquet(DATA_DIR / "statement_tag_link.parquet")


@import_register.register("statement_export", group=ImportOrder.EXPORT)
def export_statements(quiet: bool = False, update_since: datetime.date | None = None):
    """
    Export statement-related data to Parquet files
    """
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)

    dump_statement_models(quiet)
