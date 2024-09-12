from typing import Any, Callable, Optional, Type, TypeVar

from django.urls import URLPattern, URLResolver, path
from django.views.generic import View

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

        def inner(view: ViewClass) -> ViewClass:
            path_item = path(
                route, view.as_view(), kwargs=kwargs, name=name or view.__name__
            )
            self.urls[0].append(path_item)
            return view

        return inner
