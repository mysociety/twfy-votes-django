from __future__ import annotations

from enum import StrEnum


class PolicyStrength(StrEnum):
    """
    This is the strength of the relationship between the motion and the policy.
    Labelled strong and weak for historical purposes - but the precise meaning of that in a policy
    is defined by strength meaning at the policy level.
    """

    WEAK = "weak"
    STRONG = "strong"


class StrengthMeaning(StrEnum):
    """
    We have changed what strong and weak means overtime.
    This is for keeping track of a policy's current conversion status.
    """

    CLASSIC = "classic"  # old public whip style
    SIMPLIFIED = "simplified"  # Only strong votes count for big stats, weak votes are informative


class PolicyDirection(StrEnum):
    """
    This is the relatonship between the motion and the policy.
    Agree means that if the motion passes it's good for the policy.
    """

    AGREE = "agree"
    AGAINST = "against"
    NEUTRAL = "neutral"


class ChamberSlug(StrEnum):
    COMMONS = "commons"
    LORDS = "lords"
    SCOTLAND = "scotland"
    WALES = "senedd"
    NI = "ni"

    @classmethod
    def from_parlparse(cls, parlparse: str, *, passthrough: bool = False) -> str:
        match parlparse:
            case "house-of-commons":
                return cls.COMMONS
            case "house-of-lords":
                return cls.LORDS
            case "scottish-parliament":
                return cls.SCOTLAND
            case "welsh-parliament":
                return cls.WALES
            case "northern-ireland-assembly":
                return cls.NI
            case _:
                if passthrough:
                    return parlparse
                else:
                    raise ValueError(f"Unknown parlparse chamber {parlparse}")


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    DRAFT = "draft"
    REJECTED = "rejected"
    RETIRED = "retired"


class DecisionType(StrEnum):
    DIVISION = "division"
    AGREEMENT = "agreement"


class PolicyGroupSlug(StrEnum):
    HEALTH = "health"
    MISC = "misc"
    SOCIAL = "social"
    REFORM = "reform"
    FOREIGNPOLICY = "foreignpolicy"
    ENVIRONMENT = "environment"
    EDUCATION = "education"
    TAXATION = "taxation"
    BUSINESS = "business"
    TRANSPORT = "transport"
    HOUSING = "housing"
    HOME = "home"
    JUSTICE = "justice"
    WELFARE = "welfare"


class AyeNo(StrEnum):
    AYE = "aye"
    NO = "no"


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


class OrganisationType(StrEnum):
    CHAMBER = "chamber"
    PARTY = "party"
    METRO = "metro"
    UNKNOWN = "unknown"
