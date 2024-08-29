import datetime
from enum import StrEnum

from pydantic import BaseModel, computed_field


class ChamberSlug(StrEnum):
    COMMONS = "commons"
    LORDS = "lords"
    SCOTLAND = "scotland"
    WALES = "wales"
    NI = "ni"


class VotePosition(StrEnum):
    AYE = "aye"
    NO = "no"
    ABSTENTION = "abstention"
    ABSENT = "absent"
    TELLNO = "tellno"
    TELLAYE = "tellaye"
    COLLECTIVE = "collective"  # used for votes where the whole chamber votes as one


class VoteType(StrEnum):
    """
    Enum for different types of parlimentary vote.
    Not all of these are formal descriptions.
    Converging on 'stages' rather than readings across Parliament.

    """

    AMENDMENT = "amendment"
    TEN_MINUTE_RULE = "ten_minute_rule"
    LORDS_AMENDMENT = (
        "lords_amendment"  # not an amendment in the lords, but commons responding to it
    )
    FIRST_STAGE = "first_stage"
    SECOND_STAGE = "second_stage"
    COMMITEE_CLAUSE = "committee_clause"
    SECOND_STAGE_COMMITTEE = (
        "second_stage_committee"  # approval of clauses in committee
    )
    THIRD_STAGE = "third_stage"
    APPROVE_STATUTORY_INSTRUMENT = "approve_statutory_instrument"
    REVOKE_STATUTORY_INSTRUMENT = "revoke_statutory_instrument"  # negative procedure
    ADJOURNMENT = "adjournment"
    TIMETABLE_CHANGE = (
        "timetable_change"  # tracking motions that take control of the order paper
    )
    HUMBLE_ADDRESS = "humble_address"
    GOVERNMENT_AGENDA = "government_agenda"  # monarch's speech etc
    FINANCIAL = "financial"
    CONFIDENCE = "confidence"
    STANDING_ORDER_CHANGE = "standing_order_change"
    PRIVATE_SITTING = "private_sitting"
    EU_DOCUMENT_SCRUTINY = "eu_document_scrutiny"  # historically, a vote noting a document was a requirement before a minister could support in council
    OTHER = "other"

    def display_name(self):
        return self.replace("_", " ").title()


class ManualMotion(BaseModel):
    chamber: ChamberSlug
    division_date: datetime.date
    division_number: int
    manual_motion: str


class GovernmentParties(BaseModel):
    chamber: list[str]
    party: list[str]
    start_date: datetime.date
    end_date: datetime.date


class Chamber(BaseModel):
    slug: ChamberSlug

    @computed_field
    @property
    def member_name(self) -> str:
        match self.slug:
            case ChamberSlug.COMMONS:
                return "MPs"
            case ChamberSlug.LORDS:
                return "Lords"
            case ChamberSlug.SCOTLAND:
                return "MSPs"
            case ChamberSlug.WALES:
                return "MSs"
            case ChamberSlug.NI:
                return "AMs"
            case _:
                raise ValueError(f"Invalid house slug {self.slug}")

    @computed_field
    @property
    def name(self) -> str:
        match self.slug:
            case ChamberSlug.COMMONS:
                return "House of Commons"
            case ChamberSlug.LORDS:
                return "House of Lords"
            case ChamberSlug.SCOTLAND:
                return "Scottish Parliament"
            case ChamberSlug.WALES:
                return "Senedd"
            case ChamberSlug.NI:
                return "Northern Ireland Assembly"
            case _:
                raise ValueError(f"Invalid house slug {self.slug}")

    def pw_alias(self):
        # Alias for internal debate storage
        match self.slug:
            case ChamberSlug.COMMONS:
                return "debate"
            case _:
                return self.twfy_alias()

    def twfy_alias(self):
        # Alias for internal debate storage
        match self.slug:
            case ChamberSlug.COMMONS:
                return "debates"
            case ChamberSlug.LORDS:
                return "lords"
            case ChamberSlug.SCOTLAND:
                return "sp"
            case ChamberSlug.WALES:
                return "senedd"
            case ChamberSlug.NI:
                return "ni"
            case _:
                raise ValueError(f"Invalid house slug {self.slug}")

    def twfy_debate_link(self, gid: str) -> str:
        return f"https://www.theyworkforyou.com/{self.twfy_alias()}/?id={gid}"
