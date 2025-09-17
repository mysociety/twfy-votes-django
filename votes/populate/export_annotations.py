import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd

from ..models import (
    VoteAnnotation,
)
from .register import ImportOrder, import_register

STATIC_DIR = Path(settings.STATIC_ROOT)

DATA_DIR = STATIC_DIR / "data"


def export_vote_annotations(destination: Path, quiet: bool = False):
    """
    Export vote annotations with structured data including division_key, person_id and contextual information.
    """
    vote_annotations = VoteAnnotation.objects.all().select_related(
        "division", "division__chamber", "person"
    )

    if not vote_annotations.exists():
        if not quiet:
            print("No vote annotations found to export")
        return

    # Create structured data with meaningful fields
    annotation_data = []
    for annotation in vote_annotations:
        annotation_data.append(
            {
                "annotation_id": annotation.id,
                "division_key": annotation.division.key,
                "division_id": annotation.division_id,
                "person_id": annotation.person_id,
                "chamber_slug": annotation.division.chamber_slug,
                "date": annotation.division.date,
                "division_number": annotation.division.division_number,
                "detail": annotation.detail,
                "link": annotation.link,
            }
        )

    # Convert to DataFrame and export
    df = pd.DataFrame(annotation_data)
    df.to_parquet(destination)

    if not quiet:
        print(f"Exported {len(annotation_data)} vote annotations")


def dump_models(quiet: bool = False):
    # Export VoteAnnotations with structured data
    if not quiet:
        print("Exporting vote annotations")
    export_vote_annotations(DATA_DIR / "vote_annotations.parquet", quiet=quiet)


@import_register.register("export_annotations", group=ImportOrder.EXPORT)
def export_annotations(quiet: bool = False, update_since: datetime.date | None = None):
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)

    export_vote_annotations(DATA_DIR / "vote_annotations.parquet", quiet=quiet)
