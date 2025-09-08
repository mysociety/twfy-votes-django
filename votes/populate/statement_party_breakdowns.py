import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.duck import DuckQuery
from votes.models import Organization, Statement, StatementPartyBreakdown

from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")
statements_party_breakdown_parquet = compiled_dir / "statements_party_breakdown.parquet"

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_alias
class votes_statement:
    alias_for = "postgres_db.votes_statement"


@duck.as_alias
class votes_signature:
    alias_for = "postgres_db.votes_signature"


@duck.as_alias
class votes_people:
    alias_for = "postgres_db.votes_person"


@duck.as_alias
class votes_membership:
    alias_for = "postgres_db.votes_membership"


@duck.as_view
class v_signatures_with_date:
    """
    Get signatory counts per party for each statement
    """

    query = """
    SELECT
        votes_signature.* exclude (date),
        signed_date: coalesce(votes_signature.date, votes_statement.date),
    FROM votes_signature
    join votes_statement on votes_statement.id = votes_signature.statement_id
    """


@duck.as_view
class v_signatures_with_party:
    """
    Join signatures with people and their parties
    """

    query = """
    SELECT
        v_signatures_with_date.*,
        party_slug: coalesce(votes_membership.party_slug, 'unknown')
    FROM 
        v_signatures_with_date
    LEFT JOIN votes_membership on (
        votes_membership.person_id = v_signatures_with_date.person_id
        and v_signatures_with_date.signed_date between votes_membership.start_date and votes_membership.end_date
    )
    WHERE
        v_signatures_with_date.signed_date >= getvariable('start_date')
    """


@duck.to_parquet(dest=statements_party_breakdown_parquet)
class v_signature_breakdowns:
    """
    Get signatory counts per party for each statement
    """

    query = """
    SELECT
        statement_id,
        party_slug,
        signatory_count: count(*)
    FROM
        v_signatures_with_party
    GROUP BY
        statement_id, party_slug
    """


@duck.as_query
class test_query:
    query = "Select * from v_signatures_with_date"


@import_register.register("statement_party_breakdowns", group=ImportOrder.BREAKDOWNS)
def import_statement_party_breakdowns(
    quiet: bool = False, update_since: datetime.date | None = None
):
    """
    Import statement party breakdowns, optionally filtering by statement date >= since_date (YYYY-MM-DD).
    """
    with DuckQuery.connect() as query:
        if update_since:
            start_date = update_since.isoformat()
        else:
            start_date = "1900-01-01"
        query.compile(f"SET VARIABLE start_date = '{start_date}';").run()
        query.compile(duck).run()
    df = pd.read_parquet(statements_party_breakdown_parquet)
    # If since_date is provided, filter to only statements on or after that date
    if update_since:
        # Get statement dates from DB (or parquet if available)
        statement_ids_in_scope = Statement.objects.filter(
            date__gte=update_since
        ).values_list("id", flat=True)
        # Filter df
        df = df[df["statement_id"].isin(statement_ids_in_scope)]
    party_id_lookup = Organization.id_from_slug("slug")

    to_create = []
    for _, row in df.iterrows():
        to_create.append(
            StatementPartyBreakdown(
                statement_id=row["statement_id"],
                party_id=party_id_lookup[row["party_slug"]],
                count=row["signatory_count"],
            )
        )

    StatementPartyBreakdown.objects.all().delete()
    StatementPartyBreakdown.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(
            f"Created [green]{len(to_create)}[/green] statement party breakdowns"
        )
