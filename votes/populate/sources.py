import time
from pathlib import Path

from django.conf import settings

import httpx
import pandas as pd
import rich

from .register import ImportOrder, import_register

to_fetch = [
    "https://www.theyworkforyou.com/pwdata/votes/divisions.parquet",
    "https://www.theyworkforyou.com/pwdata/votes/votes.parquet",
    "https://raw.githubusercontent.com/mysociety/parlparse/master/members/people.json",
    "https://www.theyworkforyou.com/pwdata/scrapedjson/edm/proposals.parquet",
    "https://www.theyworkforyou.com/pwdata/scrapedjson/edm/signatures.parquet",
]


def download_file(
    url: str, target_path: Path, quiet: bool = False, max_retries: int = 5
) -> bool:
    """
    Download a file with retry logic and support for resuming downloads.
    """
    # Try with resume capability first
    for attempt in range(max_retries):
        try:
            # Check if we can resume
            start_byte = 0
            headers = {}
            file_mode = "wb"

            if attempt > 0 and target_path.exists() and target_path.stat().st_size > 0:
                start_byte = target_path.stat().st_size
                headers["Range"] = f"bytes={start_byte}-"
                file_mode = "ab"
                if not quiet:
                    rich.print(
                        f"Attempt {attempt+1}/{max_retries}: Resuming from [yellow]{start_byte}[/yellow] bytes"
                    )
            else:
                # First attempt or fresh download attempt
                if attempt > 0 and not quiet:
                    rich.print(
                        f"Attempt {attempt+1}/{max_retries}: Starting fresh download"
                    )

            # Use a longer timeout for larger files
            with httpx.stream(
                "GET", url, timeout=httpx.Timeout(90.0), headers=headers
            ) as response:
                # Check if request was successful
                if not response.is_success and not (
                    start_byte > 0 and response.status_code == 206
                ):
                    if not quiet:
                        rich.print(
                            f"[red]Server returned status code: {response.status_code}[/red]"
                        )
                    # For server errors, retry immediately
                    if response.status_code >= 500:
                        continue
                    else:
                        # For client errors (4xx), don't retry
                        return False

                expected_size = int(response.headers.get("content-length", 0))
                if not quiet:
                    total_size = (
                        expected_size + start_byte if start_byte > 0 else expected_size
                    )
                    rich.print(f"Downloading [blue]{url}[/blue] ({total_size} bytes)")

                # Download the file
                with target_path.open(file_mode) as f:
                    downloaded = 0
                    try:
                        # Use a smaller chunk size to avoid timeouts
                        for chunk in response.iter_bytes(chunk_size=4096):
                            f.write(chunk)
                            downloaded += len(chunk)
                    except (
                        httpx.HTTPError,
                        httpx.NetworkError,
                        httpx.TimeoutException,
                    ) as e:
                        if not quiet:
                            rich.print(f"[red]Download interrupted: {e}[/red]")
                        # Wait before retrying
                        backoff_time = 2**attempt
                        if not quiet:
                            rich.print(f"Waiting {backoff_time}s before retry...")
                        time.sleep(backoff_time)
                        continue

                # Success! Download completed
                return True

        except (httpx.HTTPError, httpx.NetworkError, httpx.TimeoutException) as e:
            if not quiet:
                rich.print(f"[red]Connection error: {e}[/red]")
            # Wait before retrying
            backoff_time = 2**attempt
            if not quiet:
                rich.print(f"Waiting {backoff_time}s before retry...")
            time.sleep(backoff_time)

    # If we get here, all retries failed
    if not quiet:
        rich.print(f"[red]Failed to download {url} after {max_retries} attempts[/red]")
    return False


@import_register.register("sources", group=ImportOrder.DOWNLOAD_PEOPLE_VOTES)
def get_external_data(quiet: bool = False):
    BASE_DIR = Path(settings.BASE_DIR)

    source_dir = BASE_DIR / "data" / "source"

    if not source_dir.exists():
        source_dir.mkdir(parents=True, exist_ok=True)

    for url in to_fetch:
        filename = url.split("/")[-1]
        target = source_dir / filename

        if not quiet:
            rich.print(f"Processing [blue]{filename}[/blue]")

        success = download_file(url, target, quiet)

        if success and not quiet:
            rich.print(
                f"[green]Successfully downloaded[/green] [blue]{filename}[/blue]"
            )
        else:
            if not quiet:
                rich.print(
                    f"[red]Failed to download {url} after multiple attempts[/red]"
                )
                rich.print("[yellow]Continuing with next file...[/yellow]")

    # patches divisions file
    # we're missing some old relevant policy ids because the gid id is missing in
    # the twfy hansard table

    legacy_df = pd.read_json(Path(BASE_DIR, "data", "lookups", "legacy_divisions.json"))

    date_columns = ["division_date", "lastupdate"]

    for d in date_columns:
        legacy_df[d] = pd.to_datetime(legacy_df[d])

    df = pd.read_parquet(source_dir / "divisions.parquet")
    df = pd.concat([df, legacy_df], ignore_index=True)
    df.to_parquet(source_dir / "divisions.parquet", index=False)
