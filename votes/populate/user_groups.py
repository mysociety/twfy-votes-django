from django.contrib.auth.models import Group

import rich

from ..consts import PermissionGroupSlug
from .register import ImportOrder, import_register


@import_register.register("user_groups", group=ImportOrder.USER_GROUPS)
def add_user_groups(quiet: bool = False):
    for g in PermissionGroupSlug:
        Group.objects.get_or_create(name=g)
    if not quiet:
        rich.print(f"[green]{len(PermissionGroupSlug)}[/green] user groups added.")
