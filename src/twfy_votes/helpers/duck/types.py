from pathlib import Path
from typing import (
    Any,
    NamedTuple,
    NewType,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    runtime_checkable,
)

from aioduckdb import Connection
from duckdb import DuckDBPyConnection
from pandas import DataFrame
from typing_extensions import Self

from .url import DuckUrl

T = TypeVar("T")

ConnectionType = DuckDBPyConnection | Connection

PathLike = Path | str
UrlLike = DuckUrl | str
FileSourceType = PathLike | UrlLike


class CompiledJinjaSQL(NamedTuple):
    query: str
    bind_params: tuple[Any, ...]


class QueryToCache(NamedTuple):
    dest: Path
    query: str


class PyArrowLike(Protocol):
    """
    Standin for pyarrow.Table which doesn't have good typing
    """

    @classmethod
    def from_pylist(
        cls,
        mapping: list[dict[str, Any]],
        schema: None | list[Tuple[str, Any]] = None,
        metadata: None | dict[str, Any] = None,
    ) -> Self: ...


DataSource = DataFrame | PyArrowLike


class DataSourceValue(NamedTuple):
    """
    Basic store for mapping a DataStore to name for import
    """

    name: str
    item: DataSource


@runtime_checkable
class PythonDataSourceProtocol(Protocol):
    """
    When the source is the instance source attribute
    """

    @property
    def source(self) -> DataSource: ...


@runtime_checkable
class PythonDataSourceCallableProtocol(Protocol):
    """
    When the instance of a class has a method get_source that returns a data source
    """

    def get_source(self) -> DataSource: ...


PythonDataSource = TypeVar(
    "PythonDataSource",
    bound=PythonDataSourceProtocol | PythonDataSourceCallableProtocol,
)


@runtime_checkable
class DuckView(Protocol):
    query: str


@runtime_checkable
class DuckAlias(Protocol):
    alias_for: str


@runtime_checkable
class DuckViewInstance(Protocol):
    @property
    def query(self) -> str: ...


@runtime_checkable
class DuckAliasInstance(Protocol):
    @property
    def alias_for(self) -> str: ...


@runtime_checkable
class DuckMacro(Protocol):
    args: list[str]
    macro: str


class BaseModelLike(Protocol):
    @classmethod
    def model_validate(cls: Type[T], obj: Any) -> T: ...

    def model_dump(self) -> dict[str, Any]: ...


BaseModelLikeType = TypeVar("BaseModelLikeType", bound=BaseModelLike)


@runtime_checkable
class SourceView(Protocol):
    source: FileSourceType


@runtime_checkable
class SourceViewInstance(Protocol):
    @property
    def source(self) -> FileSourceType: ...


DuckViewType = TypeVar("DuckViewType", bound=DuckView | DuckViewInstance)
DuckAliasView = TypeVar("DuckAliasView", bound=DuckAlias | DuckAliasInstance)
SourceViewType = TypeVar("SourceViewType", bound=SourceView | SourceViewInstance)
DuckorSourceViewType = TypeVar(
    "DuckorSourceViewType",
    bound=DuckView | DuckViewInstance | SourceView | SourceViewInstance,
)

SQLQuery = NewType("SQLQuery", str)
ViewQuery = NewType("ViewQuery", str)
TableQuery = NewType("TableQuery", str)
MacroQuery = NewType("MacroQuery", str)

PrepQuery = ViewQuery | TableQuery | MacroQuery
