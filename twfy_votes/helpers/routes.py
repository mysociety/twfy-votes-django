import re
from datetime import date
from typing import Any, Callable, Optional, Type, TypeVar

from django.urls import URLPattern, URLResolver, path, register_converter
from django.views.generic import View


class ISODateConverter:
    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        return date.fromisoformat(value)

    def to_url(self, value: date) -> str:
        return value.isoformat()


class StringNotJson:
    """
    checks if it's a lowercase string that doesn't end in .json
    """

    regex = r"[a-z0-9.]+(?<!\.json)"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value


register_converter(ISODateConverter, "date")
register_converter(StringNotJson, "str_not_json")


ViewClass = TypeVar("ViewClass", bound=Type[View])


class RouteApp:
    def __init__(self, app_name: str, namespace: str = "") -> None:
        self.urls: tuple[list[URLPattern | URLResolver], str, str] = (
            [],
            namespace,
            app_name,
        )

    def route(
        self,
        route: str,
        *,
        kwargs: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> Callable[[ViewClass], ViewClass]:
        if kwargs is None:
            kwargs = {}

        # need to convert any {year:int} to <int:year>
        route = re.sub(r"{(\w+):(\w+)}", r"<\2:\1>", route)

        # and any just plain {year} to <year>
        route = re.sub(r"{(\w+)}", r"<\1>", route)

        def inner(view: ViewClass) -> ViewClass:
            path_item = path(
                route, view.as_view(), kwargs=kwargs, name=name or view.__name__
            )
            self.urls[0].append(path_item)
            return view

        return inner
