# Register your models here.
from django.contrib import admin

from .models import AnalysisOverride, Update

admin.site.register(Update)


@admin.register(AnalysisOverride)
class DivisionOverrideAdmin(admin.ModelAdmin):
    list_display = ("id", "decision_key", "banned_motion_ids", "parl_dynamics_group")
