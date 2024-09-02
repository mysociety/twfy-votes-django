from __future__ import annotations

from typing import Literal


class DuckUrl:
    """
    Basic helper class to flag something is a URL.
    """

    def __init__(self, url: str, file_format: Literal["csv", "parquet"] | None = None):
        # check is https
        if not url.startswith("https://"):
            raise ValueError("URL must start with https://")
        self.url = url
        if file_format:
            self.format = file_format
        else:
            self.format = url.split(".")[-1]

    def __str__(self) -> str:
        return self.url

    # if a divide operator used, treat like pathlib's Path
    def __truediv__(self, other: str) -> "DuckUrl":
        # check and remove a trailing slash
        if self.url.endswith("/"):
            url = self.url[:-1]
        else:
            url = self.url
        return DuckUrl(f"{url}/{other}")
