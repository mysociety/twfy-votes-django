from __future__ import annotations

from enum import IntEnum, StrEnum


class PermissionGroupSlug(StrEnum):
    CAN_VIEW_DRAFT = "can_view_draft"  # can view draft features and info
    ADVANCED_INFO = "advanced_info"  # can view extra ids and other admin info
    CAN_REPORT_WHIP = "can_report_whip"  # can add whipreports
    CAN_REPORT_SELF_WHIP = "can_report_self_whip"  # can add self whipreports
    CAN_ADD_ANNOTATIONS = "can_add_annotations"  # can add annotations
    CAN_ADD_SELF_ANNOTATIONS = "can_add_self_annotations"  # can add self annotations
    CAN_BULK_EDIT_ANNOTATIONS = "can_bulk_edit_annotations"  # can bulk edit annotations
    CAN_ADD_STATEMENT = "can_add_statement"  # can add statements
    CAN_ADD_SIGNATORIES = (
        "can_add_signatories"  # can add signatories to existing statements
    )


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
    OTHER = "other"

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


class StrVotePosition(StrEnum):
    AYE = "aye"
    NO = "no"
    ABSTAIN = "abstain"
    ABSENT = "absent"
    TELLNO = "tellno"
    TELLAYE = "tellaye"
    COLLECTIVE = "collective"  # used for votes where the whole chamber votes as one


class RebellionPeriodType(IntEnum):
    ALLTIME = 0
    YEAR = 1
    PERIOD = 2


class VotePosition(IntEnum):
    AYE = 1
    NO = 2
    ABSTAIN = 3
    ABSENT = 4
    TELLNO = 5
    TELLAYE = 6
    COLLECTIVE = 7  # used for votes where the whole chamber votes as one


class MotionType(StrEnum):
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
    ADD_CLAUSE_TO_BILL = "add_clause_to_bill"  # second reading of a clause in report
    THIRD_STAGE = "third_stage"
    CLOSURE = "closure"
    PROGRAMME = "programme"
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
    PROPOSED_CLAUSE = "proposed_clause"
    BILL_INTRODUCTION = "bill_introduction"
    UNKNOWN = "unknown"
    REASONED_AMENDMENT = "reasoned_amendment"
    REASONS_COMMITTEE = "reasons_committee"

    def url_slug(self):
        return self.value.replace("_", "-")

    def display_name(self):
        return self.value.replace("_", " ").title()


class PowersAnalysis(StrEnum):
    USES_POWERS = "uses_powers"
    DOES_NOT_USE_POWERS = "does_not_use_powers"
    INSUFFICENT_INFO = "insufficent_info"

    def simple(self) -> bool | None:
        if self == self.USES_POWERS:
            return True
        if self == self.DOES_NOT_USE_POWERS:
            return False
        return None

    def simple_str(self) -> str:
        match self.simple():
            case True:
                return "Yes"
            case False:
                return "No"
            case None:
                return "Unknown"

    def display_name(self):
        text = self.value.replace("_powers", "_parliamentary_powers")
        return text.replace("_", " ").title()


class IssueType(StrEnum):
    STRONG_WITHOUT_POWER = "strong_without_power"
    NO_STRONG_VOTES = "no_strong_votes"
    NO_STRONG_VOTES_AFTER_POWER_CHANGE = "no_strong_votes_after_power_change"
    STRONG_VOTE_GOV_AGENDA = "strong_vote_gov_agenda"
    ONLY_ONE_STRONG_VOTE = "only_one_strong_vote"


class StatementType(StrEnum):
    PROPOSED_MOTION = "proposed_motion"
    PROPOSED_AMENDMENT = "proposed_amendment"
    LETTER = "letter"
    OTHER = "other"


class OrganisationType(StrEnum):
    CHAMBER = "chamber"
    PARTY = "party"
    METRO = "metro"
    UNKNOWN = "unknown"


class TagType(StrEnum):
    GOV_CLUSTERS = "gov_clusters"
    STATEMENT_TAGS = "statement_tags"
    MISC = "misc"
    LEGISLATION = "legislation"


class WhipPriority(StrEnum):
    """
    This is the priority of the whip.
    """

    FREE = "free"
    ONE_LINE = "one_line"  # one line whip - preferred vote with no strong attendance
    TWO_LINE = "two_line"  # two line, rare - instruct to attend without preference
    THREE_LINE = (
        "three_line"  # three line - instruct to attend and vote with preference
    )
    UNKNOWN = "unknown"  # unknown whip priority


class EvidenceType(StrEnum):
    REP = "from_rep"
    WHIP = "from_whip"
    REPORTING = "from_reporting"
    OTHER = "from_other"


class WhipDirection(StrEnum):
    """
    This is the direction of the whip.
    """

    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"
    FREE = "free"
