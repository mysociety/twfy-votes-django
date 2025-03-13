import datetime
from pathlib import Path
from typing import Callable

from django.conf import settings

import pandas as pd
import rich

from twfy_votes.helpers.detector import AndPhraseDetector, PhraseDetector

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


approve_si = AndPhraseDetector(criteria=["be approved", "laid before this house"])

revoke_si = AndPhraseDetector(criteria=["be revoked", "laid before this house"])

reasoned_amendment = PhraseDetector(
    criteria=[
        "reasoned amendment",
        "declines to give the bill a",
        "declines to give a second reading",
        AndPhraseDetector(criteria=["second reading", "this house declines to give"]),
    ],
)

timetable_change = PhraseDetector(
    criteria=["makes provision as set out in this order"],
)

standing_order_change = PhraseDetector(
    criteria=[
        "following standing order be made",
        "orders be standing orders of the house",
    ],
)

first_reading = PhraseDetector(
    criteria=["first reading"],
)

closure = PhraseDetector(
    criteria=["claimed to move the closure"],
)

second_stage_committee = AndPhraseDetector(
    criteria=[
        PhraseDetector(criteria=["second reading", "read a second time"]),
        "clause",
    ]
)

committee_clause = PhraseDetector(criteria=["clause stand part of the bill"])

programme_change = PhraseDetector(
    criteria=["that the following provisions shall apply to the"],
)

third_stage = PhraseDetector(
    criteria=["third reading", "read a third time", "read the third time"],
)

second_stage = PhraseDetector(
    criteria=["second reading", "read a second time"],
)

ten_minute_rule = AndPhraseDetector(
    criteria=["standing order", "23"],
)

ten_minute_rule = PhraseDetector(
    criteria=["standing order", "23"],
)

adjournment = PhraseDetector(
    criteria=["do adjourn until", "do now adjourn"],
)

european_document = PhraseDetector(
    criteria=[
        PhraseDetector(
            criteria=[
                "takes note of european union document",
                "takes note of european document",
                "takes note of draft european council decision",
            ],
        ),
        PhraseDetector(
            criteria=["takes note of regulation", "of the european parliament"]
        ),
    ]
)

gracious_speech = PhraseDetector(
    criteria=["gracious speech"],
)

lords_amendment = PhraseDetector(criteria=["lords", "amendment"], operator="and")

any_amendment = PhraseDetector(criteria=["amendment", "clause be added to the bill"])

humble_address = PhraseDetector(criteria=["humble address be presented"])

private_sitting = PhraseDetector(
    criteria=["that the house sit in private", "Standing Order No. 163"]
)

confidence = PhraseDetector(criteria=["confidence in the government"])

financial = PhraseDetector(
    criteria=[
        "be granted to his Majesty to be issued by the treasury out of the consolidated fund"
    ]
)

new_clause = PhraseDetector(criteria=["new clause"])

bill_introduction = PhraseDetector(criteria=["that leave be given to bring in a bill"])

# this is in priority order, the first matched will be used
criteria_map: dict[Callable[[str], bool], MotionType] = {
    approve_si: MotionType.APPROVE_STATUTORY_INSTRUMENT,
    revoke_si: MotionType.REVOKE_STATUTORY_INSTRUMENT,
    reasoned_amendment: MotionType.REASONED_AMENDMENT,
    timetable_change: MotionType.TIMETABLE_CHANGE,
    standing_order_change: MotionType.STANDING_ORDER_CHANGE,
    first_reading: MotionType.FIRST_STAGE,
    closure: MotionType.CLOSURE,
    second_stage_committee: MotionType.SECOND_STAGE_COMMITTEE,
    committee_clause: MotionType.COMMITEE_CLAUSE,
    programme_change: MotionType.PROGRAMME,
    third_stage: MotionType.THIRD_STAGE,
    second_stage: MotionType.SECOND_STAGE,
    ten_minute_rule: MotionType.TEN_MINUTE_RULE,
    adjournment: MotionType.ADJOURNMENT,
    european_document: MotionType.EU_DOCUMENT_SCRUTINY,
    gracious_speech: MotionType.GOVERNMENT_AGENDA,
    lords_amendment: MotionType.LORDS_AMENDMENT,
    any_amendment: MotionType.AMENDMENT,
    humble_address: MotionType.HUMBLE_ADDRESS,
    private_sitting: MotionType.PRIVATE_SITTING,
    confidence: MotionType.CONFIDENCE,
    financial: MotionType.FINANCIAL,
    new_clause: MotionType.PROPOSED_CLAUSE,
    bill_introduction: MotionType.BILL_INTRODUCTION,
}


def catagorise_motion(motion: str) -> MotionType:
    l_motion = motion.lower()

    for detector, motion_type in criteria_map.items():
        if detector(l_motion):
            return motion_type

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
    to_delete.delete()
    Motion.objects.bulk_create(to_create, batch_size=10000)

    if not quiet:
        rich.print(f"Imported [green]{len(to_create)}[/green] motions")
