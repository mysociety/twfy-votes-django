import datetime
from pathlib import Path

from django.conf import settings

import pandas as pd
import rich

from ..consts import MotionType
from ..models import Motion
from .register import ImportOrder, import_register

BASE_DIR = Path(settings.BASE_DIR)

MOTION_PATH = BASE_DIR / "data" / "source" / "motions.parquet"


def all_present(search: str, items: list[str]) -> bool:
    """
    function that takes a search string, and a list of strings,
    and returns true if all are present
    """
    return all([x in search for x in items])


def any_present(search: str, items: list[str]) -> bool:
    """
    function that takes a search string, and a list of strings,
    and returns true if any are present
    """
    return any([x in search for x in items])


def catagorise_motion(motion: str) -> MotionType:
    l_motion = motion.lower()
    if all_present(l_motion, ["be approved", "laid before this house"]):
        return MotionType.APPROVE_STATUTORY_INSTRUMENT
    elif all_present(l_motion, ["be revoked", "laid before this house"]):
        return MotionType.REVOKE_STATUTORY_INSTRUMENT
    elif any_present(l_motion, ["reasoned amendment", "declines to give the bill a"]):
        return MotionType.REASONED_AMENDMENT
    elif any_present(l_motion, ["makes provision as set out in this order"]):
        return MotionType.TIMETABLE_CHANGE
    elif any_present(
        l_motion,
        ["following standing order be made", "orders be standing orders of the house"],
    ):
        return MotionType.STANDING_ORDER_CHANGE
    elif any_present(l_motion, ["first reading"]):
        return MotionType.FIRST_STAGE
    elif any_present(
        l_motion, ["second reading", "read a second time"]
    ) and any_present(l_motion, ["clause"]):
        return MotionType.SECOND_STAGE_COMMITTEE
    elif any_present(l_motion, ["clause stand part of the bill"]):
        return MotionType.COMMITEE_CLAUSE
    elif any_present(
        l_motion, ["third reading", "read a third time", "read the third time"]
    ):
        return MotionType.THIRD_STAGE
    elif any_present(l_motion, ["second reading", "read a second time"]):
        return MotionType.SECOND_STAGE
    elif all_present(l_motion, ["standing order", "23"]):
        return MotionType.TEN_MINUTE_RULE
    elif any_present(l_motion, ["do adjourn until", "do now adjourn"]):
        return MotionType.ADJOURNMENT
    elif any_present(
        l_motion,
        [
            "takes note of european union document",
            "takes note of european document",
            "takes note of draft european council decision",
        ],
    ) or all_present(
        l_motion, ["takes note of regulation", "of the european parliament"]
    ):
        return MotionType.EU_DOCUMENT_SCRUTINY
    elif any_present(l_motion, ["gracious speech"]):
        return MotionType.GOVERNMENT_AGENDA
    elif all_present(l_motion, ["amendment", "lords"]):
        return MotionType.LORDS_AMENDMENT
    elif any_present(l_motion, ["amendment", "clause be added to the bill"]):
        return MotionType.AMENDMENT
    elif any_present(l_motion, ["humble address be presented"]):
        return MotionType.HUMBLE_ADDRESS
    elif any_present(l_motion, ["that the house sit in private"]):
        return MotionType.PRIVATE_SITTING
    elif all_present(l_motion, ["confidence in", "government"]):
        return MotionType.CONFIDENCE
    elif all_present(
        l_motion,
        [
            "be granted to his Majesty to be issued by the treasury out of the consolidated fund"
        ],
    ):
        return MotionType.FINANCIAL
    elif l_motion.startswith("new clause"):
        return MotionType.PROPOSED_CLAUSE
    elif any_present(l_motion, ["that leave be given to bring in a bill"]):
        return MotionType.BILL_INTRODUCTION
    else:
        return MotionType.OTHER


@import_register.register("motions", group=ImportOrder.MOTIONS)
def import_motions(quiet: bool = False, update_since: datetime.date | None = None):
    df = pd.read_parquet(MOTION_PATH)

    df["motion_type"] = df["motion_text"].apply(catagorise_motion)

    to_create: list[Motion] = []

    for _, row in df.iterrows():
        to_create.append(
            Motion(
                gid=row["gid"],
                speech_id=row["speech_id"],
                date=datetime.date.fromisoformat(row["date"]),
                title=row["motion_title"],
                text=row["motion_text"],
                motion_type=row["motion_type"],
            )
        )

    gid_count = len(set([x.gid for x in to_create]))
    if gid_count != len(to_create):
        dupe_count = len(to_create) - gid_count
        raise ValueError(f"There are duplicate gids: {dupe_count}")

    if update_since:
        to_delete = Motion.objects.filter(date__gte=update_since)
        to_create = [x for x in to_create if x.date >= update_since]
    else:
        to_delete = Motion.objects.all()

    to_create = Motion.get_lookup_manager("gid").add_ids(to_create)
    with Motion.disable_constraints():
        to_delete.delete()
        Motion.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] motions")
