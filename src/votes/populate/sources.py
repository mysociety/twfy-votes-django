from pathlib import Path

from django.conf import settings

import httpx
import rich

from .register import ImportOrder, import_register

to_fetch = [
    "https://www.theyworkforyou.com/pwdata/votes/divisions.parquet",
    "https://www.theyworkforyou.com/pwdata/votes/votes.parquet",
    "https://raw.githubusercontent.com/mysociety/parlparse/master/members/people.json",
    "https://pages.mysociety.org/parl-motion-detector/data/parliamentary_motions/latest/agreements.parquet",
    "https://pages.mysociety.org/parl-motion-detector/data/parliamentary_motions/latest/motions.parquet",
    "https://pages.mysociety.org/parl-motion-detector/data/parliamentary_motions/latest/division-links.parquet",
]


@import_register.register("sources", group=ImportOrder.DOWNLOAD)
def get_external_data(quiet: bool = False):
    BASE_DIR = Path(settings.BASE_DIR)

    source_dir = BASE_DIR / "data" / "source"

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
