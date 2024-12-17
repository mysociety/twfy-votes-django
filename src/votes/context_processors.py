from django.http import HttpRequest

from .views.auth import can_view_draft_content


def extra_context(request: HttpRequest) -> dict:
    return {
        "can_view_draft_content": can_view_draft_content(request.user),
    }
