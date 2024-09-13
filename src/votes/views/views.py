from django.views.generic import TemplateView

from twfy_votes.helpers.routes import RouteApp

from .mixins import TitleMixin

app = RouteApp(app_name="votes")


@app.route("", name="home")
class HomePageView(TitleMixin, TemplateView):
    page_title = ""
    template_name = "votes/home.html"
