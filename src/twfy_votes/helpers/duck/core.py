"""
Helper functions for interacting with sync and async duckdb connections.

You can use a basic DuckQuery to construct and store queries.

For things that actually talk to duckdb, call factory methods instead.

DuckQuery.connect()
and DuckQuery.async_create() will create a new async connection.

"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Generic, Type, TypeVar

import aioduckdb
import duckdb
from jinja2.environment import Template

from .funcs import (
    get_compiled_query,
    get_name,
    get_postgres_attach,
    query_to_macro,
    query_to_parquet,
    query_to_table,
    query_to_view,
    source_to_query,
)
from .response import AsyncDuckResponse, DuckResponse, ResponseType
from .types import (
    CompiledJinjaSQL,
    ConnectionType,
    DataSourceValue,
    DuckAliasView,
    DuckMacro,
    DuckorSourceViewType,
    DuckView,
    DuckViewInstance,
    DuckViewType,
    PythonDataSource,
    PythonDataSourceCallableProtocol,
    QueryToCache,
    SourceView,
    SourceViewInstance,
    SourceViewType,
)
from .url import DuckUrl

T = TypeVar("T")


class DuckQuery:
    def __init__(
        self,
        *,
        postgres_database_settings: dict[str, str] | None = None,
    ):
        self.queries: list[str] = []
        self.source_lookup: list[str] = []
        self.data_sources: list[DataSourceValue] = []
        self.queries_to_cache: list[QueryToCache] = []

        if postgres_database_settings:
            self.queries.append(get_postgres_attach(postgres_database_settings))

    @classmethod
    async def _async_create_connection(cls, database: str):
        connection = await aioduckdb.connect(database)
        await connection.execute("INSTALL httpfs")
        return connection

    @classmethod
    async def async_create(
        cls, connection: Any = None, database: str = ":memory:"
    ) -> ConnectedDuckQuery[AsyncDuckResponse]:
        if not connection:
            connection = await cls._async_create_connection(database)
        return ConnectedDuckQuery[AsyncDuckResponse](
            connection=connection, response_type=AsyncDuckResponse
        )

    @classmethod
    def connect(
        cls,
        connection: ConnectionType | None = None,
        database: str = ":memory:",
    ) -> ConnectedDuckQuery[DuckResponse]:
        if not connection:
            connection = duckdb.connect(database)

        return ConnectedDuckQuery[DuckResponse](
            connection=connection, response_type=DuckResponse
        )

    def construct_query(self, variables: dict[str, Any] = {}) -> CompiledJinjaSQL:
        complex_query = ";".join(self.queries)

        if variables:
            complex_query = get_compiled_query(complex_query, variables)
        else:
            complex_query = CompiledJinjaSQL(query=complex_query, bind_params=tuple())

        return complex_query

    def as_table_macro(self, item: Type[DuckMacro]):
        """
        Decorator to store a macro as part of a longer running query
        """
        return self.as_macro(item, table=True)

    def as_macro(self, item: Type[DuckMacro], table: bool = False) -> Type[DuckMacro]:
        name = get_name(item)

        args = getattr(item, "args", None)

        if args is None:
            raise ValueError("Macro must have an args attribute")

        macro = getattr(item, "macro", None)

        if macro is None:
            raise ValueError("Macro must have a macro method")

        # this is a very boring substitution
        # but makes it more obvious in the template where the variables are
        # not strictly needed to function
        macro = Template(macro).render({x: x for x in args})

        if not macro:
            raise ValueError("Macro tempalte returns nothing")

        query = query_to_macro(name, args, macro, table=table)
        self.queries.append(query)

        return item

    def as_python_source(self, item: PythonDataSource) -> PythonDataSource:
        if isinstance(item, PythonDataSourceCallableProtocol):
            source = item.get_source()
        else:
            source = item.source
        table_name = get_name(item)
        self.data_sources.append(
            DataSourceValue(name="_source_" + table_name, item=source)
        )

        table_query = f"CREATE OR REPLACE TABLE {table_name} AS (SELECT * FROM _source_{table_name})"

        self.queries.append(table_query)

        return item

    def as_source(
        self, item: Type[SourceViewType], to_table: bool = False
    ) -> Type[SourceViewType]:
        """
        Decorator to store a source as part of a longer running query
        """

        name = get_name(item)
        source = getattr(item, "source", None)

        if isinstance(source, str):
            # if starts with http, treat as a url
            if source.startswith("http"):
                source = DuckUrl(source)
            else:
                source = Path(source)

        if source is None:
            raise ValueError("Class must have a source attribute")

        if to_table:
            query_func = query_to_table
        else:
            query_func = query_to_view

        query = query_func(source_to_query(source), name=name)
        self.queries.append(query)
        return item

    def as_view(
        self, item: Type[DuckViewType], as_table: bool = False
    ) -> Type[DuckViewType]:
        """
        Decorator to stash a view as part of a longer running query
        """

        name = get_name(item)
        query = getattr(item, "query", None)

        if query is None:
            raise ValueError("Class must have a query method")

        self.source_lookup.append(name)
        if as_table:
            store_as_view = query_to_table(query, name=name)
        else:
            store_as_view = query_to_view(query, name=name)
        self.queries.append(store_as_view)

        return item

    def to_parquet(
        self, dest: Path, *, reuse_as_source: bool = False
    ) -> Callable[[Type[DuckViewType]], Type[DuckViewType]]:
        """
        Render this view to parquet path.
        """

        def inner(item: Type[DuckViewType]) -> Type[DuckViewType]:
            query = getattr(item, "query", None)
            name = get_name(item)

            if query is None:
                raise ValueError("Class must have a query method")

            self.queries.append(query_to_parquet(query, dest))

            if reuse_as_source:
                query = query_to_view(source_to_query(dest), name=name)
                self.queries.append(query)

            return item

        return inner

    def as_alias(self, item: Type[DuckAliasView]) -> Type[DuckAliasView]:
        """
        Decorator to store a view as part of a longer running query
        """

        name = get_name(item)
        alias_for = getattr(item, "alias_for", None)

        if alias_for is None:
            raise ValueError("Class must have a alias_for method")

        query = f"CREATE OR REPLACE VIEW {name} AS (SELECT * FROM {alias_for})"
        self.queries.append(query)

        return item

    def as_query(self, item: Type[DuckViewType]) -> Type[DuckViewType]:
        """
        Decorator to convert something implementing DuckView to a DuckResponse
        """

        query = getattr(item, "query", None)

        if query is None:
            raise ValueError("Class must have a query method")

        self.queries.append(query)

        return item

    def as_table(self, item: Type[DuckorSourceViewType]) -> Type[DuckorSourceViewType]:
        """
        Decorator to convert something implementing SourceView to a DuckResponse
        """
        if isinstance(item, DuckView | DuckViewInstance):
            return self.as_view(item, as_table=True)
        elif isinstance(item, SourceView | SourceViewInstance):
            return self.as_source(item, to_table=True)
        else:
            raise ValueError("Can only use as_table on a DuckView or SourceView")


class ConnectedDuckQuery(DuckQuery, Generic[ResponseType]):
    def __init__(
        self,
        connection: ConnectionType,
        response_type: Type[ResponseType],
    ):
        super().__init__()

        self.response_type = response_type
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def get_view(self, name: str | Type[DuckView]) -> ResponseType:
        if isinstance(name, str):
            view_name = name
        else:
            view_name = get_name(name)
        return self.compile(query=f"SELECT * FROM {view_name}")

    def compile(
        self,
        query: str | DuckQuery | Type[DuckView] | DuckViewInstance,
        variables: dict[str, Any] = {},
    ) -> ResponseType:
        if hasattr(query, "query"):
            _query = getattr(query, "query")
            if hasattr(query, "params"):
                _params = getattr(query, "params")
                _query = get_compiled_query(_query, _params)
        elif isinstance(query, DuckQuery):
            _query = query.construct_query(variables)
            self.data_sources += query.data_sources
            self.queries_to_cache += query.queries_to_cache
        elif isinstance(query, str):
            _query = query
            if variables:
                _query = get_compiled_query(_query, variables)
        else:
            raise ValueError(
                "Can only compile a string, DuckQuery or object with a 'query' property"
            )

        if len(self.queries) > 0:
            raise ValueError("Can only use 'compile' on a fresh or empty query.")
        return self.response_type(self.connection, _query, self.data_sources)  # type: ignore

    query = compile

    def close(self):
        self.connection.close()

    def compile_queue(self, variables: dict[str, Any] = {}) -> ResponseType:
        _query = self.construct_query(variables)
        self.queries = []
        return self.response_type(self.connection, _query, self.data_sources)  # type: ignore
