import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd

from ..models import (
    WhipReport,
)
from .register import ImportOrder, import_register

STATIC_DIR = Path(settings.STATIC_ROOT)

DATA_DIR = STATIC_DIR / "data"


def export_whip_reports(destination: Path, quiet: bool = False):
    """
    Export whip reports with structured data including division_key, party information and contextual information.
    """
    whip_reports = WhipReport.objects.all().select_related(
        "division", "division__chamber", "party"
    )

    if not whip_reports.exists():
        if not quiet:
            print("No whip reports found to export")
        return

    # Create structured data with meaningful fields
    whip_data = []
    for whip_report in whip_reports:
        whip_data.append(
            {
                "whip_report_id": whip_report.id,
                "division_key": whip_report.division.key,
                "division_id": whip_report.division_id,
                "party_id": whip_report.party_id,
                "party_name": whip_report.party.name,
                "party_slug": whip_report.party.slug,
                "chamber_slug": whip_report.division.chamber_slug,
                "date": whip_report.division.date,
                "division_number": whip_report.division.division_number,
                "whip_direction": whip_report.whip_direction,
                "whip_priority": whip_report.whip_priority,
                "evidence_type": whip_report.evidence_type,
                "evidence_detail": whip_report.evidence_detail,
            }
        )

    # Convert to DataFrame and export
    df = pd.DataFrame(whip_data)
    df.to_parquet(destination)

    if not quiet:
        print(f"Exported {len(whip_data)} whip reports")


def dump_models(quiet: bool = False):
    # Export WhipReports with structured data
    if not quiet:
        print("Exporting whip reports")
    export_whip_reports(DATA_DIR / "whip_reports.parquet", quiet=quiet)


@import_register.register("export_whip_reports", group=ImportOrder.EXPORT)
def export_whip_reports_task(
    quiet: bool = False, update_since: datetime.date | None = None
):
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)

    export_whip_reports(DATA_DIR / "whip_reports.parquet", quiet=quiet)
