from typing import Any, TypeVar

import aioduckdb
import duckdb
import numpy as np
import pandas as pd

from .types import CompiledJinjaSQL, DataSourceValue, SQLQuery


def dataframe_to_dict_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert a DataFrame into a list of dictionaries.

    This is a dumber but faster approach than then to_dict method.
    Because we know the columns are basic types, we can just iterate over the rows
    """
    cols = list(df)
    col_arr_map = {col: df[col].astype(object).to_numpy() for col in cols}
    records = []
    for i in range(len(df)):
        record = {col: col_arr_map[col][i] for col in cols}
        records.append(record)

    return records


class DuckResponse:
    def __init__(
        self,
        connection: Any,
        query: str | CompiledJinjaSQL,
        data_sources: list[DataSourceValue] | None = None,
    ):
        self._connection = connection
        if isinstance(query, str):
            self._query = SQLQuery(query)
            self._params = None
        else:
            self._query = query.query
            self._params = query.bind_params
        self._params = self._params or []
        self._response = None
        self.data_sources = data_sources if data_sources else []

    @property
    def response(self) -> duckdb.DuckDBPyConnection:
        for df in self.data_sources:
            self._connection.register(df.name, df.item)
        if self._response is None:
            self._response = self.get_response()
        return self._response

    def get_response(self) -> duckdb.DuckDBPyConnection:
        return self._connection.execute(self._query, self._params)

    def __iter__(self) -> Any:
        return iter(self.response.fetchall())

    def df(self) -> pd.DataFrame:
        return self.response.df()

    def fetchone(self) -> Any:
        return self.response.fetchone()[0]  # type: ignore

    def fetch_df(self) -> pd.DataFrame:
        return self.response.df()

    def fetch_int(self) -> int:
        return int(self.fetchone())

    def fetch_bool(self) -> bool:
        return bool(self.fetchone())

    def fetch_float(self) -> float:
        return float(self.fetchone())

    def fetch_str(self) -> str:
        return str(self.fetchone())

    def int(self) -> int:
        return self.fetch_int()

    def str(self) -> str:
        return self.fetch_str()

    def bool(self) -> bool:
        return self.fetch_bool()

    def float(self) -> float:
        return self.fetch_float()

    def run(self) -> None:
        """
        Execute but return nothing
        """
        self.get_response()


class AsyncDuckResponse:
    def __init__(
        self,
        connection: aioduckdb.Connection,
        query: str | CompiledJinjaSQL,
        data_sources: list[DataSourceValue] | None = None,
    ):
        self._connection = connection
        if isinstance(query, str):
            self._query = SQLQuery(query)
            incoming_params = None
        else:
            self._query = query.query
            incoming_params = query.bind_params
        self._params = incoming_params or []

        self.data_sources = data_sources if data_sources else []

    async def get_response(self, execute_on_self: bool = False):
        if execute_on_self:
            # for initial database population
            # As a first time thing, this registered and makes accessible
            # to the queued query which will move it to the main database
            while self.data_sources:
                df = self.data_sources.pop(0)
                await self._connection.register(df.name, df.item)
            cursor = await self._connection.execute_on_self(self._query, self._params)
        else:
            cursor = await self._connection.cursor()
            cursor = await cursor.execute(self._query, self._params)
        return cursor

    async def __aiter__(self) -> Any:
        cursor = await self.get_response()
        async for row in cursor.fetchall():  # type: ignore
            yield row

    async def df(self) -> pd.DataFrame:
        cursor = await self.get_response()
        df = await cursor.df()
        await cursor.close()

        return df

    async def records(self, nan_to_none: bool = False) -> list[dict[str, Any]]:
        df = await self.df()
        if nan_to_none:
            df = df.fillna(np.nan).replace([np.nan], [None])
        return dataframe_to_dict_records(df)

    async def first_record(self) -> dict[str, Any]:
        df = await self.df()
        return df.to_dict(orient="records")[0]  # type: ignore

    async def fetchone(self) -> Any:
        cursor = await self.get_response()
        result = await cursor.fetchone()
        await cursor.close()
        return result[0]  # type: ignore

    async def fetch_df(self) -> pd.DataFrame:
        return await self.df()

    async def fetch_int(self) -> int:
        return int(await self.fetchone())

    async def fetch_bool(self) -> bool:
        return bool(await self.fetchone())

    async def fetch_float(self) -> float:
        return float(await self.fetchone())

    async def fetch_str(self) -> str:
        return str(await self.fetchone())

    async def int(self) -> int:
        return await self.fetch_int()

    async def str(self) -> str:
        return await self.fetch_str()

    async def bool(self) -> bool:
        return await self.fetch_bool()

    async def float(self) -> float:
        return await self.fetch_float()

    async def run(self) -> None:
        """
        Execute but return nothing
        """
        await self.get_response()

    async def run_on_self(self) -> None:
        """
        Execute but return nothing
        Runs on the main connection rather than a cursor
        """
        await self.get_response(execute_on_self=True)


ResponseType = TypeVar("ResponseType", DuckResponse, AsyncDuckResponse)
