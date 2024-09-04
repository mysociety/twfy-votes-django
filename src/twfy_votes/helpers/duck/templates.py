from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Type, TypeVar, get_type_hints

from jinja2.environment import Template
from typing_extensions import dataclass_transform

from .core import AsyncDuckResponse, ConnectedDuckQuery
from .funcs import unnest
from .response import ResponseType
from .types import BaseModelLikeType

T = TypeVar("T")


@dataclass_transform(kw_only_default=True)
class BaseQuery:
    """
    Base class to create a reusable query using jinja syntax

    Expects a 'query_template' class variable, and then dataclass style
    declarations of the variables to be used in the template.

    e.g.

    class ExampleQuery(BaseQuery):
        query_template = "Select {{ column }} from {{ table }}"
        column: str
        table: str

    """

    class validate(str, Enum):
        ONLY_ONE = "only_one"
        NOT_ZERO = "not_zero"
        NO_VALIDATION = "NO_VALIDATION"

    query_template = ""

    def __init__(self, **kwargs: Any):
        hints = get_type_hints(self.__class__)

        default_args = {
            h: getattr(self.__class__, h)
            for h in hints.keys()
            if hasattr(self.__class__, h)
        }

        # if any of the default args are not in kwargs, add them

        for k, v in default_args.items():
            if k not in kwargs:
                kwargs[k] = v

        # if any of the kwargs are not in the hints, raise an error
        cls_name = self.__class__.__name__
        for k in kwargs:
            if k not in hints:
                raise TypeError(f"{cls_name} got an unexpected keyword argument '{k}'")

        # if no value for an expected argument is provided, raise an error

        for h in hints.keys():
            if h not in kwargs:
                raise TypeError(f"{cls_name} missing required keyword argument '{h}'")

        # check we have a template
        if not self.query_template:
            raise NotImplementedError(
                "BaseQuery must be subclassed with a query_template attribute"
            )

        self.query = self.query_template
        self.params = kwargs

    async def run(self, duck: ConnectedDuckQuery[AsyncDuckResponse]):
        return await duck.compile(self, variables=self.params).run()

    def compile(self, duck: ConnectedDuckQuery[ResponseType]) -> ResponseType:
        return duck.compile(self, variables=self.params)

    async def pipe_records_to(
        self,
        duck: ConnectedDuckQuery[AsyncDuckResponse],
        func: Callable[[dict[str, Any]], T],
        unnest_record: bool = True,
        nan_to_none: bool = False,
    ) -> list[T]:
        """
        Pipe the records from a query to a function.

        If unnest_record is True, the records will be unnested first - django stype.

        e.g. {'a__b__c': 1} -> {'a': {'b': {'c': 1}}

        """
        records = await duck.compile(self, variables=self.params).records(
            nan_to_none=nan_to_none
        )
        if unnest_record:
            records = [unnest(r) for r in records]
        return [func(r) for r in records]

    pipe_to = pipe_records_to

    async def to_model_list(
        self,
        *,
        model: Type[BaseModelLikeType],
        duck: ConnectedDuckQuery[AsyncDuckResponse],
        validate: validate = validate.NO_VALIDATION,
        nan_to_none: bool = False,
    ) -> list[BaseModelLikeType]:
        validate_options = self.__class__.validate

        records = await self.pipe_records_to(
            duck, model.model_validate, nan_to_none=nan_to_none
        )

        if validate == validate_options.ONLY_ONE:
            if len(records) == 0:
                raise ValueError(
                    f"No items found for model {model.__name__}. One expected."
                )
            elif len(records) > 1:
                raise ValueError(
                    f"Multiple items found for model {model.__name__}. One expected."
                )

        elif validate == validate_options.NOT_ZERO:
            if len(records) == 0:
                raise ValueError(
                    f"No items found for model {model.__name__}. One or more expected."
                )

        return records

    async def to_model_single(
        self,
        *,
        model: Type[BaseModelLikeType],
        duck: ConnectedDuckQuery[AsyncDuckResponse],
    ) -> BaseModelLikeType:
        """
        Return a single model instance from a query.
        Only works if there is only one valid response to a query.
        """
        records = await self.to_model_list(
            model=model, duck=duck, validate=self.__class__.validate.ONLY_ONE
        )
        return records[0]


class RawJinjaQuery(BaseQuery):
    """
    This version will render the jinja2 at this point.
    Useful for queries that can't be prepared - but generally better to
    instead prepare macros and then call from a normal query.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.query = Template(self.query_template).render(**self.params)
