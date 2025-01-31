import datetime
from hashlib import md5
from typing import Any, Generic, TypeVar

from pydantic import AliasChoices, BaseModel, Field, computed_field

from votes.consts import (
    ChamberSlug,
    DecisionType,
    PolicyDirection,
    PolicyGroupSlug,
    PolicyStatus,
    PolicyStrength,
    StrengthMeaning,
)


def aliases(*args: str) -> Any:
    return Field(..., validation_alias=AliasChoices(*args))


class PartialDivision(BaseModel):
    """
    Base instance of the properties needed to identify a division
    """

    chamber_slug: ChamberSlug
    date: datetime.date = aliases("date", "division_date")
    division_number: int

    @computed_field
    @property
    def key(self) -> str:
        return f"pw-{self.date.isoformat()}-{self.division_number}-{self.chamber_slug}"


class PartialAgreement(BaseModel):
    chamber_slug: ChamberSlug
    date: datetime.date = aliases("date", "division_date")
    decision_ref: str  # The bit after the date in the TWF ref
    division_name: str = ""  # Here so this model can be used to load from YAML - not used to promote to AgreementInfo

    @computed_field
    @property
    def key(self) -> str:
        return f"a-{self.chamber_slug}-{self.date.isoformat()}-{self.decision_ref}"


PartialDecisionType = TypeVar("PartialDecisionType", PartialAgreement, PartialDivision)


class PartialPolicyDecisionLink(BaseModel, Generic[PartialDecisionType]):
    policy_id: int | None = None
    decision: PartialDecisionType
    alignment: PolicyDirection
    strength: PolicyStrength = PolicyStrength.WEAK
    notes: str = ""

    def decision_type(self) -> str:
        match self.decision:
            case PartialDivision():
                return DecisionType.DIVISION
            case PartialAgreement():
                return DecisionType.AGREEMENT
            case _:
                raise ValueError("Must have agreement or division")

    @computed_field
    @property
    def decision_key(self) -> str:
        return self.decision.key

    def link_key(self) -> str:
        return f"{self.decision_key}-{self.alignment}-{self.strength}"


class PartialPolicy(BaseModel):
    """
    Version of policy object for reading and writing from basic storage.
    Doesn't store full details of related decisions etc.
    """

    id: int = Field(
        description="Preverse existing public whip ids as URLs reflect these in TWFY. New ID should start at 10000"
    )

    name: str
    context_description: str
    policy_description: str
    notes: str = ""
    status: PolicyStatus
    strength_meaning: StrengthMeaning = StrengthMeaning.SIMPLIFIED
    highlightable: bool = Field(
        description="Policy can be drawn out as a highlight on page if no calculcated 'interesting' votes"
    )
    chamber: ChamberSlug
    groups: list[PolicyGroupSlug]
    division_links: list[PartialPolicyDecisionLink[PartialDivision]]
    agreement_links: list[PartialPolicyDecisionLink[PartialAgreement]]

    def composite_key(self) -> str:
        division_keys = [link.link_key() for link in self.division_links]
        agreement_keys = [link.link_key() for link in self.agreement_links]
        all_keys = division_keys + agreement_keys
        all_keys.sort()
        policy_key = f"{self.id}-{self.chamber}-{self.strength_meaning}"
        joined_keys = "-".join(all_keys)
        return f"{policy_key}-{joined_keys}"

    def composite_hash(self) -> str:
        return md5(self.composite_key().encode()).hexdigest()[:8]

    def model_dump_reduced(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """
        Tidy up YAML representation a bit
        """
        di = self.model_dump(*args, **kwargs)

        for ref in di["division_links"]:
            if ref["decision"]:
                del ref["decision"]["key"]
            del ref["decision_key"]
        return di
