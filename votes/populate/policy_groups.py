import rich

from ..consts import PolicyGroupSlug
from ..models.decisions import PolicyGroup
from .register import ImportOrder, import_register

description_lookup = {
    PolicyGroupSlug.BUSINESS: "Business and the Economy",
    PolicyGroupSlug.REFORM: "Constitutional Reform",
    PolicyGroupSlug.EDUCATION: "Education",
    PolicyGroupSlug.ENVIRONMENT: "Environmental Issues",
    PolicyGroupSlug.TAXATION: "Taxation and Employment",
    PolicyGroupSlug.FOREIGNPOLICY: "Foreign Policy and Defence",
    PolicyGroupSlug.HEALTH: "Health",
    PolicyGroupSlug.HOME: "Home Affairs",
    PolicyGroupSlug.HOUSING: "Housing",
    PolicyGroupSlug.JUSTICE: "Justice",
    PolicyGroupSlug.MISC: "Miscellaneous Topics",
    PolicyGroupSlug.SOCIAL: "Social Issues",
    PolicyGroupSlug.WELFARE: "Welfare, Benefits and Pensions",
    PolicyGroupSlug.TRANSPORT: "Transport",
}


@import_register.register("policy_group", group=ImportOrder.LOOKUPS)
def import_policy_groups(quiet: bool = False):
    to_create = []

    for slug, description in description_lookup.items():
        group = PolicyGroup(slug=slug, description=description)
        to_create.append(group)

    if not quiet:
        rich.print(f"Creating [green]{len(to_create)}[/green] policy groups")

    to_create = PolicyGroup.get_lookup_manager("slug").add_ids(to_create)

    with PolicyGroup.disable_constraints():
        PolicyGroup.objects.all().delete()
        PolicyGroup.objects.bulk_create(to_create, batch_size=1000)
    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] policy groups")
