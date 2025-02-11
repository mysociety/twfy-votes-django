import rich

from ..consts import ChamberSlug
from ..models import Chamber
from .register import ImportOrder, import_register

member_name_lookup = {
    ChamberSlug.COMMONS: "MPs",
    ChamberSlug.LORDS: "Lords",
    ChamberSlug.SCOTLAND: "MSPs",
    ChamberSlug.WALES: "MSs",
    ChamberSlug.NI: "AMs",
}

chamber_name_lookup = {
    ChamberSlug.COMMONS: "House of Commons",
    ChamberSlug.LORDS: "House of Lords",
    ChamberSlug.SCOTLAND: "Scottish Parliament",
    ChamberSlug.WALES: "Senedd",
    ChamberSlug.NI: "Northern Ireland Assembly",
}


@import_register.register("chambers", group=ImportOrder.CHAMBERS)
def import_chambers(quiet: bool = False):
    existing_ids = Chamber.id_from_slug(slug_field="slug")

    to_create = []

    for slug in ChamberSlug:
        group = Chamber(
            slug=slug,
            member_plural=member_name_lookup[slug],
            name=chamber_name_lookup[slug],
        )
        group.id = existing_ids.get(slug, None)
        to_create.append(group)

    to_create = Chamber.get_lookup_manager("slug").add_ids(to_create)

    Chamber.objects.all().delete()
    Chamber.objects.bulk_create(to_create, batch_size=1000)
    if not quiet:
        rich.print(f"Created [green]{len(to_create)}[/green] chambers")
