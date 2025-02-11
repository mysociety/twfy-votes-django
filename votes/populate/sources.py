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
]


@import_register.register("sources", group=ImportOrder.DOWNLOAD_PEOPLE_VOTES)
def get_external_data(quiet: bool = False):
    BASE_DIR = Path(settings.BASE_DIR)

    source_dir = BASE_DIR / "data" / "source"

    if not source_dir.exists():
        source_dir.mkdir(parents=True, exist_ok=True)

    for url in to_fetch:
        filename = url.split("/")[-1]
        target = source_dir / filename
        # use httpx to download the file
        if not quiet:
            rich.print(f"Downloading [blue]{url}[/blue] to [blue]{target}[/blue]")
        with httpx.stream("GET", url) as response:
            with target.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)

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
