import datetime
import inspect
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

import rich


def accepts_argument(func: Callable[[Any], Any], arg_name: str):
    """Check if a function accepts a specific argument."""
    try:
        # Get the function signature
        signature = inspect.signature(func)
        # Check if the argument is in the function's parameters
        return arg_name in signature.parameters
    except Exception as e:
        # Handle any exceptions that might arise (e.g., if func is not callable)
        print(f"Error inspecting function: {e}")
        return False


class ImportOrder(IntEnum):
    DOWNLOAD = 1
    CHAMBERS = 4
    PEOPLE = 5
    LOOKUPS = 10
    MOTIONS = 13
    API_VOTES = 14
    DECISIONS = 15
    PRE_BREAKDOWNS = 16
    BREAKDOWNS = 17
    DIVISION_ANALYSIS = 18
    VOTES = 19
    PERSON_STATS = 20
    POLICIES = 23
    PREP_POLICYCALC = 25
    POLICYCALC = 30


@runtime_checkable
class AcceptsQuiet(Protocol):
    def __call__(self, quiet: bool) -> None: ...


@runtime_checkable
class AcceptsUpdate(Protocol):
    def __call__(
        self, quiet: bool, update_since: datetime.date | None = None
    ) -> None: ...


RegisterFunc = TypeVar("RegisterFunc", bound=AcceptsQuiet | AcceptsUpdate)


@dataclass
class ImportRegister:
    import_functions: dict[str, AcceptsQuiet] = field(default_factory=dict)
    groups: dict[ImportOrder, list[str]] = field(default_factory=dict)

    def register(
        self, name: str, group: ImportOrder
    ) -> Callable[[RegisterFunc], RegisterFunc]:
        if group not in self.groups:
            self.groups[group] = []
        self.groups[group].append(name)

        def decorator(func: RegisterFunc) -> RegisterFunc:
            self.import_functions[name] = func
            return func

        return decorator

    def run_import(
        self, slug: str, quiet: bool = False, update_since: datetime.date | None = None
    ) -> None:
        func = self.import_functions[slug]
        if not quiet:
            rich.print(f"[blue]Running {slug}[/blue]")
        if accepts_argument(func, "update_since"):
            func(quiet=quiet, update_since=update_since)  # type: ignore
        elif accepts_argument(func, "quiet"):
            func(quiet=quiet)
        else:
            raise TypeError(
                f"Function {slug} does not accept 'quiet' or 'update_since'"
            )

    def run_group(
        self, group: str, quiet: bool = False, update_since: datetime.date | None = None
    ) -> None:
        import_order = ImportOrder[group.upper()]

        to_run = self.groups[import_order]
        tuples = [(slug, self.import_functions[slug]) for slug in to_run]
        for slug, func in tuples:
            if not quiet:
                rich.print(f"[blue]Running {slug}[blue]")
            if accepts_argument(func, "update_since"):
                func(quiet=quiet, update_since=update_since)  # type: ignore
            elif accepts_argument(func, "quiet"):
                func(quiet=quiet)

    def run_group_range(
        self,
        start_group: str,
        end_group: str,
        quiet: bool = False,
        update_since: datetime.date | None = None,
    ) -> None:
        start_group_order = ImportOrder[start_group.upper()]
        end_group_order = ImportOrder[end_group.upper()]

        # iterate through ImportOrder from start_group to end_group

        for group in ImportOrder:
            if group < start_group_order:
                continue
            if group > end_group_order:
                break
            self.run_group(group.name, quiet=quiet, update_since=update_since)

    def run_all(
        self, quiet: bool = False, update_since: datetime.date | None = None
    ) -> None:
        groups = list(self.groups.keys())
        groups.sort(key=lambda x: x.value)

        for group in groups:
            self.run_group(group.name, quiet=quiet, update_since=update_since)


import_register = ImportRegister()
