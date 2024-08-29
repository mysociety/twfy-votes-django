from dataclasses import dataclass, field
from typing import Callable, NamedTuple, Protocol, TypeVar

import rich


class AcceptsVerbose(Protocol):
    def __call__(self, quiet: bool) -> None: ...


class OrderFunc(NamedTuple):
    order: int
    func: AcceptsVerbose


Verbose = TypeVar("Verbose", bound=AcceptsVerbose)


@dataclass
class ImportRegister:
    import_functions: dict[str, OrderFunc] = field(default_factory=dict)
    groups: dict[str, list[str]] = field(default_factory=dict)

    def register(
        self, name: str, group: str = "", order: int = 0
    ) -> Callable[[Verbose], Verbose]:
        if group:
            if group not in self.groups:
                self.groups[group] = []
            self.groups[group].append(name)

        def decorator(func: Verbose) -> Verbose:
            self.import_functions[name] = OrderFunc(order, func)
            return func

        return decorator

    def run_import(self, slug: str, quiet: bool = False) -> None:
        _, func = self.import_functions[slug]
        if not quiet:
            rich.print(f"[blue]Running {slug}[/blue]")
        func(quiet=quiet)

    def run_group(self, group: str, quiet: bool = False) -> None:
        to_run = self.groups[group]
        tuples = [(slug, self.import_functions[slug]) for slug in to_run]
        # sort
        tuples.sort(key=lambda x: x[1].order)
        for slug, (order, func) in tuples:
            if not quiet:
                rich.print(f"[blue]Running {slug}[blue]")
            func(quiet=quiet)

    def run_all(self, quiet: bool = False) -> None:
        all_slugs = self.import_functions.keys()
        tuples = [(slug, self.import_functions[slug]) for slug in all_slugs]
        # sort
        tuples.sort(key=lambda x: x[1].order)
        for slug, (order, func) in tuples:
            if not quiet:
                rich.print(f"[blue]Running {slug}[/blue]")
            func(quiet=quiet)


import_register = ImportRegister()
