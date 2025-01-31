from django.urls import path

from .views.api import api
from .views.views import app

urlpatterns = [path("", app.urls), path("", api.urls)]
