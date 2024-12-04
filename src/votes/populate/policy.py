import datetime
from pathlib import Path
from typing import Any, Type, cast

from django.conf import settings
from django.db import models

import rich
from ruamel.yaml import YAML

from twfy_votes.helpers.base_model import disable_constraints
from twfy_votes.policy.models import (
    PartialPolicy,
)

from ..models import (
    Agreement,
    Chamber,
    Division,
    Policy,
    PolicyAgreementLink,
    PolicyDivisionLink,
    PolicyGroup,
)
from .register import ImportOrder, import_register


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

    # Now we need to create the policy group connections - access the ThroughModel

    ThroughModel = cast(Type[models.Model], Policy.groups.through)  # type: ignore
    group_id_lookup = PolicyGroup.id_from_slug("slug")
    to_create = []

    for partial in partials:
        for group in partial.groups:
            to_create.append(
                ThroughModel(
                    policy_id=partial.id, policygroup_id=group_id_lookup[group]
                )
            )

    with disable_constraints(ThroughModel._meta.db_table):
        ThroughModel.objects.all().delete()
        ThroughModel.objects.bulk_create(to_create, batch_size=1000)

    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] policy group connection")

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
