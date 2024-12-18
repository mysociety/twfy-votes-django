from django.contrib.auth.models import Group

from .register import ImportOrder, import_register


@import_register.register("user_groups", group=ImportOrder.USER_GROUPS)
def add_user_groups(quiet: bool = False):
    groups_to_create = ["access_in_progress", "advanced_info"]

    for g in groups_to_create:
        Group.objects.get_or_create(name=g)
