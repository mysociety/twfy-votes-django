from __future__ import annotations

import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich
from tqdm import tqdm

from twfy_votes.helpers.duck import DuckQuery

from ..consts import TagType
from ..models import Division, DivisionTag
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)
compiled_dir = Path(BASE_DIR, "data", "compiled")

divisions_gov_with_counts = compiled_dir / "divisions_gov_with_counts.parquet"

division_cluster_path = compiled_dir / "division_cluster_columns.parquet"
clusters_labelled = compiled_dir / "clusters_labelled.parquet"
cluster_centers = BASE_DIR / "data" / "lookups" / "cluster_centers.csv"


duck = DuckQuery(postgres_database_settings=settings.DATABASES["default"])


@duck.as_alias
class pw_division:
    alias_for = "postgres_db.votes_division"


@duck.as_source
class pw_divisions_gov_with_counts:
    source = divisions_gov_with_counts


@duck.as_view
class reformat_for_cluster_base:
    """
    For each division, get the counts of votes for and against the motion, and absent or neutral by gov and opp
    grouping 0 = Other, 1 = Government
    """

    query = """
    select
        division_id: pw_divisions_gov_with_counts.division_id,
        opp_aye: sum(case when grouping = 0 then for_motion else 0 end),
        opp_no: sum(case when grouping = 0 then against_motion else 0 end),
        opp_other: sum(case when grouping = 0 then absent_motion + neutral_motion else 0 end),
        gov_aye: sum(case when grouping = 1 then for_motion else 0 end),
        gov_no: sum(case when grouping = 1 then against_motion else 0 end),
        gov_other: sum(case when grouping = 1 then absent_motion + neutral_motion else 0 end),
    from pw_divisions_gov_with_counts
    join pw_division on (pw_division.key = pw_divisions_gov_with_counts.division_id)
    group by pw_divisions_gov_with_counts.division_id, 
    order by pw_divisions_gov_with_counts.division_id
    """


@duck.to_parquet(dest=division_cluster_path)
class reformat_for_cluster:
    """
    Now we reexpress gov/opp voting for or against as percentages of their total number.
    This should be more robust over time and between chambers.

    grouping 0 = Other, 1 = Government
    """

    query = """
    select
        division_id: reformat_for_cluster_base.division_id,
        opp_aye_p: opp_aye / (opp_aye + opp_other + opp_no),
        opp_no_p: opp_no / (opp_aye + opp_other + opp_no),
        gov_aye_p: gov_aye / (gov_aye + gov_other + gov_no),
        gov_no_p: gov_no / (gov_aye + gov_other + gov_no),
    from reformat_for_cluster_base
    """


def get_commons_clusters(df: pd.DataFrame, quiet: bool = True) -> "pd.Series[str]":
    """
    Cluster analysis in a box.

    The cluster centers are defined through a script here
    https://github.com/mysociety/motion-cluster-analysis

    Should be relatively robust over time through.

    """

    center_df = pd.read_csv(cluster_centers, index_col="labels")

    cluster_distance: list[float] = []
    cluster_name: list[str] = []

    required_columns = list(center_df.columns)
    if len([x for x in df.columns if x in required_columns]) < 4:
        raise ValueError("Dataframe missing all required columns")
    tdf = list(df[required_columns].transpose().items())
    for _, series in tqdm(tdf, total=len(tdf), disable=quiet):
        # for each row calculate the distance to all the centroids and get the closest
        distance_series = (
            (center_df - series).pow(2).sum(axis=1).pow(1.0 / 2).sort_values()
        )
        closest_name = distance_series.index[0]
        closest_distance = distance_series.iloc[0]

        cluster_distance.append(closest_distance)
        cluster_name.append(closest_name)  # type: ignore

    # get these into a single dataframe
    cluster_name_s = pd.Series(cluster_name, index=df.index)
    cluster_distance_s = pd.Series(cluster_distance, index=df.index)

    jdf = pd.DataFrame(
        {
            "cluster": cluster_name_s,
            "distance": cluster_distance_s,
        }
    )

    # now what we want is a column that *within* each cluster puts them in a percentile of distance
    # with the smallest distance being 0 and the maximum distance being 1
    # do this because if it's tightly clustered we don't want an artifical line

    rescaled_distance_cols: list[pd.Series] = []

    for _, cluster_df in jdf.groupby("cluster"):
        max_distance = cluster_df["distance"].max()
        rescaled_distance = (cluster_df["distance"]) / max_distance
        rescaled_distance_cols.append(rescaled_distance)

    jdf["cluster_percentile"] = pd.concat(rescaled_distance_cols)

    # if cluster_percentile > 0.70 then we should consider this a weak cluster
    # and add a _outlier suffix to the cluster name
    jdf["cluster"] = jdf.apply(
        lambda x: (
            f"{x['cluster']}_outlier"
            if x["cluster_percentile"] > 0.70
            else x["cluster"]
        ),
        axis=1,
    )

    return jdf["cluster"]


@import_register.register("cluster_analysis", group=ImportOrder.DIVISION_ANALYSIS)
def import_cluster_analysis(
    quiet: bool = False, update_since: datetime.date | None = None
):
    with DuckQuery.connect() as query:
        df = query.compile(duck).run()

    division_id_lookup = Division.id_from_slug("key")
    affected_divisions = (
        Division.objects.filter(date__gte=update_since).values_list("id", flat=True)
        if update_since
        else []
    )

    df = pd.read_parquet(division_cluster_path)

    df["division_database_id"] = df["division_id"].map(division_id_lookup)

    clusters = get_commons_clusters(df, quiet=quiet)

    df["cluster"] = clusters

    df.to_parquet(clusters_labelled)

    if update_since:
        df = df[df["division_database_id"].isin(affected_divisions)]

    to_create = []

    for _, row in tqdm(df.iterrows(), total=len(df), disable=quiet):
        if update_since and row["division_database_id"] not in affected_divisions:
            continue
        item = DivisionTag(
            division_id=row["division_database_id"],
            tag_type=TagType.GOV_CLUSTERS,
            analysis_data=row["cluster"],
        )
        to_create.append(item)

    if update_since:
        DivisionTag.objects.filter(division_id__in=affected_divisions).delete()
    else:
        DivisionTag.objects.all().delete()

    DivisionTag.objects.bulk_create(to_create)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] division clusters")
