import typer
from trogon import Trogon
from typer.main import get_group

from votes.consts import (
    ChamberSlug,
    PolicyDirection,
    PolicyGroupSlug,
    PolicyStatus,
    PolicyStrength,
)

app = typer.Typer(help="", no_args_is_help=True)


@app.command()
def ui(ctx: typer.Context):
    """
    Open terminal UI
    """
    Trogon(get_group(app), click_context=ctx).run()


@app.command()
def add_vote_to_policy(
    votes_url: str,
    policy_id: int,
    vote_alignment: PolicyDirection,
    strength: PolicyStrength = PolicyStrength.STRONG,
):
    """
    Add a vote to a policy based on a twfy-votes URL.
    """
    from .tools import add_vote_to_policy_from_url

    add_vote_to_policy_from_url(
        votes_url=votes_url,
        policy_id=policy_id,
        vote_alignment=vote_alignment,
        strength=strength,
    )


@app.command()
def create_policy(
    name: str,
    context_description: str = "",
    policy_description: str = "",
    status: PolicyStatus = PolicyStatus.DRAFT,
    chamber: ChamberSlug = ChamberSlug.COMMONS,
    groups: list[PolicyGroupSlug] = [],
):
    """
    Create a new policy
    """
    from .tools import create_new_policy

    create_new_policy(
        name=name,
        context_description=context_description,
        policy_description=policy_description,
        status=status,
        chamber=chamber,
        groups=groups,
    )


if __name__ == "__main__":
    app()
