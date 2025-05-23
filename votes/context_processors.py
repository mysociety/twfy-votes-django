from django.conf import settings
from django.http import HttpRequest

from .consts import PermissionGroupSlug
from .views.auth import can_view_draft_content


def extra_context(request: HttpRequest) -> dict:
    return {
        "can_view_draft_content": can_view_draft_content(request.user),
        "request": request,
        "permission_group": PermissionGroupSlug,
        "GOOGLE_ANALYTICS": settings.GOOGLE_ANALYTICS,
    }
