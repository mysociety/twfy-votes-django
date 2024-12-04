from django.conf import settings

import environ
import pytest


@pytest.fixture(scope="session")
def django_db_setup():
    env = environ.Env(
        DEBUG=(bool, False),
        ALLOWED_HOSTS=(list, []),
        HIDE_DEBUG_TOOLBAR=(bool, False),
        GOOGLE_ANALYTICS=(str, ""),
        TWFY_API_KEY=(str, ""),
    )

    settings.DATABASES = {"default": env.db()}
