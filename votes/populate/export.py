import datetime
import json
import shutil
from pathlib import Path

from django.conf import settings

import duckdb
import httpx
import pandas as pd

from twfy_votes.helpers.duck import DuckQuery

from ..models import (
    AgreementTagLink,
    Chamber,
    DecisionTag,
    DivisionTagLink,
    Organization,
    PolicyComparisonPeriod,
    Signature,
    Statement,
    StatementTagLink,
)
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


BASE_DIR = Path(settings.BASE_DIR)

STATIC_DIR = Path(settings.STATIC_ROOT)

DATA_DIR = STATIC_DIR / "data"
VOTE_DATA_DIR = DATA_DIR / "votes"
SOURCE_DIR = BASE_DIR / "data" / "source"
COMPILED_DIR = BASE_DIR / "data" / "compiled"


@duck.as_alias
class votes:
    alias_for = "postgres_db.votes_vote"


@duck.as_alias
class divisions:
    alias_for = "postgres_db.votes_division"


@duck.as_macro
class int_to_str_vote_position:
    """
    Reverse of `str_to_int_vote_position`:
    converts the numeric vote code back to its
    human-readable string form.
    """

    args = ["int_vote_position"]
    macro = """
    CASE int_vote_position
        WHEN 1 THEN 'aye'
        WHEN 2 THEN 'no'
        WHEN 3 THEN 'abstain'
        WHEN 4 THEN 'absent'
        WHEN 5 THEN 'tellno'
        WHEN 6 THEN 'tellaye'
        WHEN 7 THEN 'collective'
        ELSE NULL
    END
    """


@duck.to_parquet(dest=DATA_DIR / "simple_memberships.parquet")
class simple_memberships:
    query = """
         SELECT
            membership_id: reverse(split_part(reverse(membership_id), '/', 1)),
            person_id: reverse(split_part(reverse(person_id), '/', 1)),
            * exclude (membership_id, person_id)
        FROM
            'https://pages.mysociety.org/politician_data/data/uk_politician_data/latest/simple_memberships.parquet'
    """


@duck.to_parquet(dest=COMPILED_DIR / "raw_vote.parquet")
class raw_vote:
    query = """
        SELECT * from votes
    """


@duck.to_parquet(dest=DATA_DIR / "divisions.parquet")
class divisions_export:
    query = """
        SELECT * from divisions
        ORDER BY key
    """


@duck.as_source
class p_votes:
    source = COMPILED_DIR / "raw_vote.parquet"


@duck.as_source
class p_divisions:
    source = DATA_DIR / "divisions.parquet"


@duck.as_table_macro
class votes_export:
    args = ["_start_date", "_end_date"]
    macro = """
        SELECT 
            division_key: divisions.key,
            vote: int_to_str_vote_position(votes.vote),
            effective_vote: int_to_str_vote_position(votes.effective_vote),
            effective_vote_float,
            diff_from_party_average,
            division_id,
            membership_id,
            person_id
        FROM
            votes: p_votes
        JOIN divisions: p_divisions on votes.division_id = divisions.id
        WHERE divisions.date >= _start_date
        AND divisions.date < _end_date
        order by division_key, person_id
    """


def export_votes(quiet: bool = False):
    """
    Export adjusted votes to Parquet files for each five year period.
    """

    start_year = 2000
    end_year = datetime.date.today().year

    if not VOTE_DATA_DIR.exists():
        VOTE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print("Exporting votes and divisions to Parquet files")
    with DuckQuery.connect() as cduck:
        cduck.compile(duck).run()
        step = 5
        for year in range(start_year, end_year + 1, step):
            if not quiet:
                print(f"Exporting votes for year {year} - {year + step - 1}")
            start_date = datetime.date(year, 1, 1)
            end_date = datetime.date(year + step, 1, 1)
            dest = VOTE_DATA_DIR / f"votes_{year}.parquet"
            query = f"""
            COPY (
            select * from votes_export('{start_date}', '{end_date}')
            ) TO '{dest}' (FORMAT PARQUET, COMPRESSION brotli)
            """
            cduck.query(query).run()

        if not quiet:
            print("Recombining to Parquet file")
        # re-assemble main votes.parquet
        votes_dest = DATA_DIR / "votes.parquet"

        query = f"""
        COPY (
        SELECT
            *
        FROM parquet_scan('{VOTE_DATA_DIR / "votes_*.parquet"}')
        ) TO '{votes_dest}' (FORMAT PARQUET, COMPRESSION brotli)
        """
        cduck.query(query).run()


def move_as_is(quiet: bool = False):
    compiled_files = [
        "division_with_counts.parquet",
        "divisions_gov_with_counts.parquet",
        "divisions_party_with_counts.parquet",
        "per_person_party_diff_all_time.parquet",
        "per_person_party_diff_period.parquet",
        "per_person_party_diff_year.parquet",
        "policy_calc_to_load.parquet",
        "clusters_labelled.parquet",
    ]

    for file in compiled_files:
        if not quiet:
            print(f"Copying {file} from compiled to data directory")
        source = COMPILED_DIR / file
        destination = DATA_DIR / file
        shutil.copyfile(source, destination)


def dump_models(quiet: bool = False):
    if not quiet:
        print("Dumping models to Parquet files")

    all_orgs = pd.DataFrame(list(Chamber.objects.all().values()))
    all_orgs.to_parquet(DATA_DIR / "chambers.parquet")

    all_orgs = pd.DataFrame(list(Organization.objects.all().values()))
    all_orgs.to_parquet(DATA_DIR / "organization.parquet")

    all_tags = pd.DataFrame(list(DecisionTag.objects.all().values()))
    all_tags.to_parquet(DATA_DIR / "tags.parquet")

    all_division_tag_links = pd.DataFrame(list(DivisionTagLink.objects.all().values()))
    all_division_tag_links["extra_data"] = all_division_tag_links["extra_data"].apply(
        json.dumps
    )
    all_division_tag_links.to_parquet(DATA_DIR / "division_tag_link.parquet")

    all_agreement_tag_links = pd.DataFrame(
        list(AgreementTagLink.objects.all().values())
    )

    if len(all_agreement_tag_links) > 0:
        all_agreement_tag_links["extra_data"] = all_agreement_tag_links[
            "extra_data"
        ].apply(json.dumps)
        all_agreement_tag_links.to_parquet(DATA_DIR / "agreement_tag_link.parquet")

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

    all_periods = pd.DataFrame(list(PolicyComparisonPeriod.objects.all().values()))
    all_periods.to_parquet(DATA_DIR / "policy_comparison_period.parquet")


def create_duckdb(quiet: bool = False):
    """
    Create a duckdb where all these URLs are available for querying.
    """

    if not quiet:
        print("Creating DuckDB with views for all votes data")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    duck_db_path = DATA_DIR / "twfy_votes.duckdb"

    # This needs to reference the live site for URLs to connect
    url_base = f"{settings.LIVE_URL}{settings.STATIC_URL}data"

    conn = duckdb.connect(database=str(duck_db_path))

    for parquet_file in DATA_DIR.glob("*.parquet"):
        table_name = parquet_file.stem
        url = f"{url_base}/{parquet_file.name}"
        # check if url exists before creating the view
        url_exists = httpx.head(url).status_code == 200
        if not url_exists:
            if not quiet:
                print(f"Skipping {table_name} as URL does not exist: {url}")
            continue

        conn.execute(
            f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_parquet('{url}')"
        )

    conn.close()


@import_register.register("export", group=ImportOrder.EXPORT)
def export_compiled(quiet: bool = False, update_since: datetime.date | None = None):
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)

    move_as_is()
    export_votes()
    dump_models()
    create_duckdb()
