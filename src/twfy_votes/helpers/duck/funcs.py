from collections import defaultdict
from pathlib import Path
from typing import Any, cast

import pandas as pd
from jinjasql import JinjaSql  # type: ignore

from .types import (
    CompiledJinjaSQL,
    FileSourceType,
    MacroQuery,
    SQLQuery,
    TableQuery,
    ViewQuery,
)
from .url import DuckUrl


def get_name(obj: Any) -> str:
    return cast(str, obj.__name__)


def nested_dict() -> defaultdict[str, Any]:
    return defaultdict(nested_dict)


def defaultdict_to_normal(di: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in di.items():
        if isinstance(v, defaultdict):
            out[k] = defaultdict_to_normal(v)
        else:
            out[k] = v
    return out


def unnest(di: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = nested_dict()

    for k, v in di.items():
        current_dict = out
        levels = k.split("__")
        level_key, final = levels[:-1], levels[-1]
        for level in level_key:
            current_dict = current_dict[level]
        current_dict[final] = v

    return defaultdict_to_normal(out)


def get_postgres_attach(database_config: dict[str, str]) -> SQLQuery:
    name = database_config["NAME"]
    user = database_config["USER"]
    password = database_config["PASSWORD"]
    host = database_config["HOST"]

    return SQLQuery(f"""
            ATTACH 'dbname={name} user={user} host={host} password={password}' AS postgres_db (TYPE POSTGRES)
            """)


def source_to_query(source: FileSourceType | str) -> SQLQuery:
    if isinstance(source, DuckUrl):
        return SQLQuery(f"SELECT * FROM '{str(source)}'")
    elif isinstance(source, Path):
        # if csv
        if source.suffix == ".csv":
            return SQLQuery(
                f"SELECT * FROM read_csv('{str(source)}', HEADER=True, AUTO_DETECT=True)"
            )
        else:
            return SQLQuery(f"SELECT * FROM '{str(source)}'")
    elif isinstance(source, pd.DataFrame):
        raise ValueError(
            "Can't convert a dataframe into a query in an abstract way, use 'register' instead"
        )
    else:
        return SQLQuery(f"SELECT * FROM '{str(source)}'")


def query_to_macro(
    name: str, args: list[str], macro: str, table: bool = False
) -> MacroQuery:
    if table:
        macro = f"table {macro}"
    return MacroQuery(
        f"""
    CREATE OR REPLACE MACRO {name}({", ".join(args)}) AS
    {macro}
    """
    )


def query_to_view(query: SQLQuery, name: str) -> ViewQuery:
    return ViewQuery(f"CREATE OR REPLACE VIEW {name} AS {query}")


def query_to_table(query: SQLQuery, name: str) -> TableQuery:
    return TableQuery(f"CREATE OR REPLACE TABLE {name} AS {query}")


class TypedJinjaSql(JinjaSql):
    def get_compiled_query(self, source: str, data: dict[str, Any]) -> CompiledJinjaSQL:
        query, bind_params = self.prepare_query(source, data)
        return CompiledJinjaSQL(query=query, bind_params=bind_params)  # type: ignore


jsql = TypedJinjaSql(param_style="asyncpg")


def get_compiled_query(source: str, data: dict[str, Any]) -> CompiledJinjaSQL:
    return jsql.get_compiled_query(source, data)
