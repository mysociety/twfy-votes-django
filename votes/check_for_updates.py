from datetime import datetime

from .models import Division, Update
from .populate.commons_votes import DivisionSearchList


def new_divisions_on_commons_votes():
    """
    Check if any new divisions are in the api
    """
    start_time = datetime.now().date()
    end_time = datetime.now().date()
    search_results = DivisionSearchList.from_date(
        start_date=start_time, end_date=end_time
    )

    our_ids = [x.pw_division_id for x in search_results]
    matches = Division.objects.filter(key__in=our_ids).count()

    if len(our_ids) > matches:
        return True
    return False


def check_for_external_update_markers():
    if new_divisions_on_commons_votes():
        Update.create_task(
            {"shortcut": " refresh_commons_api"}, created_via="Commons API trigger"
        )
    return False
