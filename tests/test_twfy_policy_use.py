from django.test.client import Client

import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.django_db


class BasicAgreement(BaseModel):
    gid: str
    house: str
    strength: str
    url: str
    division_name: str
    date: str
    alignment: str


class PolicyConfig(BaseModel):
    policies: dict[str, str]  # policy id to context_description
    set_descs: dict[str, str]  # set slug to set name
    agreements: dict[
        str, list[BasicAgreement]
    ]  # policy ids to agreements relevant to policies
    sets: dict[str, list[int]]  # set slug and list of policy ids in that slug


def test_process_twfy(client: Client):
    """
    Does the same transformation as TWFY does, tests we still produce the right
    keys and data.
    """

    response = client.get("/policies/commons/active/all.json")
    data = response.json()

    groups: dict[str, str] = {}

    policy_to_group: dict[str, list[int]] = {}
    policy_description: dict[str, str] = {}
    agreement_links: dict[str, list[BasicAgreement]] = {}

    # iterate through policies

    for policy_data in data:
        # context descriptions get stored in policies.json
        policy_description[str(policy_data["id"])] = policy_data["context_description"]

        # here we're populating the set name lookup and adding the policy to relevant groups
        for group in policy_data["groups"]:
            groups[group["slug"]] = group["description"]
            if group["slug"] not in policy_to_group:
                policy_to_group[group["slug"]] = []
            policy_to_group[group["slug"]].append(int(policy_data["id"]))

        # agreement links get stored in the json file (very few of them so far)
        for agreement in policy_data["agreement_links"]:
            decision = agreement["decision"]
            # cut off the last part of the decision ref to get the gid
            gid = ".".join(decision["decision_ref"].split(".")[:-1])
            url = f"https://www.theyworkforyou.com/debate/?id={decision['date']}{gid}"

            ba = BasicAgreement(
                gid=decision["date"] + gid,
                house=decision["chamber_slug"],
                strength=agreement["strength"],
                url=url,
                division_name=decision["decision_name"],
                date=decision["date"],
                alignment=agreement["alignment"],
            )
            str_id = str(policy_data["id"])
            if str_id not in agreement_links:
                agreement_links[str_id] = []
            agreement_links[str_id].append(ba)

    # we store a json file with the basic policy config rather than having small tables
    policy_config = PolicyConfig(
        policies=policy_description,
        set_descs=groups,
        agreements=agreement_links,
        sets=policy_to_group,
    )

    assert len(policy_config.policies) > 0, "No policies found"
    assert len(policy_config.set_descs) > 0, "No set descriptions found"
    assert len(policy_config.agreements) > 0, "No agreements found"
    assert len(policy_config.sets) > 0, "No sets found"
