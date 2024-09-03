from django.urls import path

from .views import core
from .views.api import api

urlpatterns = [
    path("", core.HomePageView.as_view(), name="home"),
    path("", api.urls),
]

print(urlpatterns)
