from __future__ import annotations

import duckdb
import pytest

from twfy_votes.helpers.duck import DuckQuery


def test_cte_pipeline_renders_and_executes_as_one_query() -> None:
    pipeline = DuckQuery()

    @pipeline.as_cte(materialized=True)
    class source_rows:
        query = "select * from values (1), (2), (3) as source(value)"

    @pipeline.as_cte(materialized=False)
    class doubled_rows:
        depends_on = [source_rows]
        query = "select value * 2 as value from source_rows"

    query = pipeline.render_ctes("select sum(value) from doubled_rows")

    assert "source_rows AS MATERIALIZED" in query
    assert "doubled_rows AS NOT MATERIALIZED" in query
    assert duckdb.connect().execute(query).fetchone() == (12,)


def test_cte_pipeline_rejects_out_of_order_dependency() -> None:
    pipeline = DuckQuery()

    class missing_stage:
        query = "select 1"

    with pytest.raises(ValueError, match="unregistered CTEs: missing_stage"):

        @pipeline.as_cte()
        class dependent_stage:
            depends_on = [missing_stage]
            query = "select * from missing_stage"


def test_cte_pipeline_rejects_duplicate_names() -> None:
    pipeline = DuckQuery()

    @pipeline.as_cte()
    class stage:
        query = "select 1"

    with pytest.raises(ValueError, match="already registered"):
        pipeline.as_cte()(stage)


def test_cte_pipeline_requires_at_least_one_stage() -> None:
    with pytest.raises(ValueError, match="No CTEs"):
        DuckQuery().render_ctes("select 1")
