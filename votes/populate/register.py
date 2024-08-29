from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Protocol, TypeVar

import rich


class ImportOrder(IntEnum):
    DOWNLOAD = 1
    LOOKUPS = 10


class AcceptsQuiet(Protocol):
    def __call__(self, quiet: bool) -> None: ...


Verbose = TypeVar("Verbose", bound=AcceptsQuiet)


@dataclass
class ImportRegister:
    import_functions: dict[str, AcceptsQuiet] = field(default_factory=dict)
    groups: dict[ImportOrder, list[str]] = field(default_factory=dict)

    def register(self, name: str, group: ImportOrder) -> Callable[[Verbose], Verbose]:
        if group not in self.groups:
            self.groups[group] = []
        self.groups[group].append(name)

        def decorator(func: Verbose) -> Verbose:
            self.import_functions[name] = func
            return func

        return decorator

    def run_import(self, slug: str, quiet: bool = False) -> None:
        func = self.import_functions[slug]
        if not quiet:
            rich.print(f"[blue]Running {slug}[/blue]")
        func(quiet=quiet)

    def run_group(self, group: str, quiet: bool = False) -> None:
        import_order = ImportOrder[group.upper()]

        to_run = self.groups[import_order]
        tuples = [(slug, self.import_functions[slug]) for slug in to_run]
        for slug, func in tuples:
            if not quiet:
                rich.print(f"[blue]Running {slug}[blue]")
            func(quiet=quiet)

    def run_all(self, quiet: bool = False) -> None:
        groups = list(self.groups.keys())
        groups.sort(key=lambda x: x.value)

        for group in groups:
            self.run_group(group.name, quiet=quiet)


import_register = ImportRegister()
