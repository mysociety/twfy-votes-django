import datetime
import json
import shutil
from pathlib import Path

from django.conf import settings

import pandas as pd

from twfy_votes.helpers.duck import DuckQuery

from ..consts import VotePosition
from ..models import (
    AgreementTagLink,
    Chamber,
    DecisionTag,
    Division,
    DivisionTagLink,
    Organization,
    PolicyComparisonPeriod,
)
from .register import ImportOrder, import_register

duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


BASE_DIR = Path(settings.BASE_DIR)

STATIC_DIR = Path(settings.STATIC_ROOT)

DATA_DIR = STATIC_DIR / "data"
SOURCE_DIR = BASE_DIR / "data" / "source"
COMPILED_DIR = BASE_DIR / "data" / "compiled"

votes_with_diff = COMPILED_DIR / "votes_with_diff.parquet"


def move_as_is():
    source_files = [
        "divisions.parquet",
        "votes.parquet",
    ]

    compiled_files = [
        "division_with_counts.parquet",
        "divisions_gov_with_counts.parquet",
        "divisions_party_with_counts.parquet",
        "per_person_party_diff_all_time.parquet",
        "per_person_party_diff_period.parquet",
        "per_person_party_diff_year.parquet",
        "policy_calc_to_load.parquet",
        "clusters_labelled.parquet",
    ]

    for file in source_files:
        source = SOURCE_DIR / file
        destination = DATA_DIR / file
        shutil.copyfile(source, destination)

    for file in compiled_files:
        source = COMPILED_DIR / file
        destination = DATA_DIR / file
        shutil.copyfile(source, destination)


def dump_models():
    all_orgs = pd.DataFrame(list(Chamber.objects.all().values()))
    all_orgs.to_parquet(DATA_DIR / "chambers.parquet")

    all_orgs = pd.DataFrame(list(Organization.objects.all().values()))
    all_orgs.to_parquet(DATA_DIR / "organization.parquet")

    all_tags = pd.DataFrame(list(DecisionTag.objects.all().values()))
    all_tags.to_parquet(DATA_DIR / "tags.parquet")

    all_division_tag_links = pd.DataFrame(list(DivisionTagLink.objects.all().values()))
    all_division_tag_links["extra_data"] = all_division_tag_links["extra_data"].apply(
        json.dumps
    )
    all_division_tag_links.to_parquet(DATA_DIR / "division_tag_link.parquet")

    all_agreement_tag_links = pd.DataFrame(
        list(AgreementTagLink.objects.all().values())
    )

    if len(all_agreement_tag_links) > 0:
        all_agreement_tag_links["extra_data"] = all_agreement_tag_links[
            "extra_data"
        ].apply(json.dumps)
        all_agreement_tag_links.to_parquet(DATA_DIR / "agreement_tag_link.parquet")

    all_periods = pd.DataFrame(list(PolicyComparisonPeriod.objects.all().values()))
    all_periods.to_parquet(DATA_DIR / "policy_comparison_period.parquet")


def improve_votes():
    div_id_to_key: dict[int, str] = dict(Division.objects.values_list("id", "key"))

    df = pd.read_parquet(votes_with_diff)

    df["division_id"] = df["division_id"].map(div_id_to_key)

    df["vote"] = df["vote"].apply(lambda x: VotePosition(x).name)
    df["effective_vote"] = df["effective_vote"].apply(lambda x: VotePosition(x).name)

    df.to_parquet(DATA_DIR / "votes_with_diff.parquet")


@import_register.register("export", group=ImportOrder.EXPORT)
def export_compiled(quiet: bool = False, update_since: datetime.date | None = None):
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)

    move_as_is()
    dump_models()
    improve_votes()
