from django.contrib.auth.models import AbstractBaseUser, AnonymousUser, User

from ..consts import PermissionGroupSlug


def super_users_or_group(user: AbstractBaseUser | AnonymousUser, group_slug: str):
    if not user.is_authenticated:
        return False
    if isinstance(user, User):
        return user.is_superuser or user.groups.filter(name=group_slug).exists()
    return False


def can_view_advanced_info(user: AbstractBaseUser | AnonymousUser):
    return super_users_or_group(user, PermissionGroupSlug.ADVANCED_INFO)


def can_view_draft_content(user: AbstractBaseUser | AnonymousUser):
    return super_users_or_group(user, PermissionGroupSlug.CAN_VIEW_DRAFT)
