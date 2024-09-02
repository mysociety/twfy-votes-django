import tempfile
from pathlib import Path

from .core import DuckQuery


def sync_to_postgres(parquet: Path, table: str, database_settings: dict[str, str]):
    """
    Copying from the parquet is much faster than an insert!

    This expects a path to parquet file with the same columns the database expects.
    """

    temp_dir = Path(tempfile.gettempdir())

    temp_dest = temp_dir / "sync.parquet"

    duck = DuckQuery(postgres_database_settings=database_settings)

    @duck.as_query
    class get_columns:
        query = f"""
            SELECT
                column_name
            FROM
                information_schema.columns
            WHERE
                table_name = '{table}'
                AND table_schema = 'public';
        """

    with DuckQuery.connect() as query:
        df = query.compile(duck).df()

    columns = df["column_name"].tolist()

    duck = DuckQuery(postgres_database_settings=database_settings)

    @duck.as_source
    class source:
        source = parquet

    @duck.to_parquet(dest=temp_dest)
    class reorder_for_upload:
        query = f"""
        SELECT
            {', '.join(columns)}
        FROM
            source
        """

    @duck.as_query
    class copy:
        query = f"""
        DELETE FROM postgres_db.{table};
        COPY postgres_db.{table} FROM '{temp_dest}';
        """

    @duck.as_query
    class check:
        query = f"""
        SELECT
            count(*)
        FROM
            postgres_db.{table}
        """

    with DuckQuery.connect() as query:
        value = query.compile(duck).int()

    temp_dest.unlink()

    return value
