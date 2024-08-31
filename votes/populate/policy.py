import datetime
from hashlib import md5
from pathlib import Path
from typing import Any, Generic, TypeVar

from django.conf import settings

import rich
from pydantic import AliasChoices, BaseModel, Field, computed_field
from ruamel.yaml import YAML

from ..consts import (
    ChamberSlug,
    DecisionType,
    PolicyDirection,
    PolicyGroupSlug,
    PolicyStatus,
    PolicyStrength,
    StrengthMeaning,
)
from ..models.decisions import (
    Agreement,
    Chamber,
    Division,
    Policy,
    PolicyAgreementLink,
    PolicyDivisionLink,
)
from .register import ImportOrder, import_register


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

    @computed_field
    @property
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
        division_keys = [link.decision.key for link in self.division_links]
        agreement_keys = [link.decision.key for link in self.agreement_links]
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


def load_policies() -> list[PartialPolicy]:
    """
    Load policies from YAML
    """
    policies_folder = Path(settings.BASE_DIR) / "data" / "policies"

    policies: list[PartialPolicy] = []

    yaml = YAML(typ="safe")  # default, if not specfied, is 'rt' (round-trip)

    for path in policies_folder.glob("*.yml"):
        data: dict[str, Any] = yaml.load(path)
        policies.append(PartialPolicy.model_validate(data))

    return policies


@import_register.register("policies", group=ImportOrder.POLICIES)
def populate_policies(quiet: bool = False) -> None:
    partials = load_policies()

    # Here we need to create two things
    # We need to create the policies

    # And the two sets of decision links

    to_create = []

    chamber_ids = Chamber.id_from_slug("slug")

    for partial in partials:
        policy = Policy(
            id=partial.id,
            name=partial.name,
            chamber_slug=partial.chamber,
            chamber_id=chamber_ids[partial.chamber],
            context_description=partial.context_description,
            policy_description=partial.policy_description,
            notes=partial.notes,
            status=partial.status,
            strength_meaning=partial.strength_meaning,
            highlightable=partial.highlightable,
            policy_hash=partial.composite_hash(),
        )
        to_create.append(policy)

    with Policy.disable_constraints():
        Policy.objects.all().delete()
        Policy.objects.bulk_create(to_create, batch_size=1000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] policies")

    division_links = []
    agreement_links = []

    division_lookup = Division.id_from_slug("key")
    agreement_lookup = Agreement.id_from_slug("key")

    weird_date_cut_off = datetime.date(2010, 1, 1)

    for partial in partials:
        for link in partial.division_links:
            # temp undtil we fix the data
            if link.decision.date < weird_date_cut_off:
                continue
            division_links.append(
                PolicyDivisionLink(
                    policy_id=partial.id,
                    decision_id=division_lookup[link.decision.key],
                    alignment=link.alignment,
                    strength=link.strength,
                    notes=link.notes,
                )
            )

        for link in partial.agreement_links:
            # temp undtil we fix the data
            if link.decision.date < weird_date_cut_off:
                continue
            agreement_links.append(
                PolicyAgreementLink(
                    policy_id=partial.id,
                    decision_id=agreement_lookup[link.decision.key],
                    alignment=link.alignment,
                    strength=link.strength,
                    notes=link.notes,
                )
            )

    with PolicyDivisionLink.disable_constraints():
        PolicyDivisionLink.objects.all().delete()
        PolicyDivisionLink.objects.bulk_create(division_links, batch_size=1000)

    if not quiet:
        rich.print(f"Created [green]{len(division_links)}[/green] division links")

    with PolicyAgreementLink.disable_constraints():
        PolicyAgreementLink.objects.all().delete()
        PolicyAgreementLink.objects.bulk_create(agreement_links, batch_size=1000)

    if not quiet:
        rich.print(f"Created [green]{len(agreement_links)}[/green] agreement links")
