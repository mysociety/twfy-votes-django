# Register your models here.
from django.contrib import admin

from .models import (
    Agreement,
    AgreementAnnotation,
    AnalysisOverride,
    Division,
    DivisionAnnotation,
    Person,
    Update,
    VoteAnnotation,
    WhipReport,
)


@admin.register(Update)
class UpdateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "date_created",
        "date_started",
        "date_completed",
        "failed",
        "instructions",
    )
    list_filter = ("failed",)


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("id", "key")
    search_fields = ("key",)


@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ("id", "key")
    search_fields = ("key",)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("id",)


@admin.register(AnalysisOverride)
class DivisionOverrideAdmin(admin.ModelAdmin):
    list_display = ("id", "decision_key", "banned_motion_ids", "parl_dynamics_group")


@admin.register(WhipReport)
class WhipReportAdmin(admin.ModelAdmin):
    list_display = ("id", "division", "party", "whip_direction", "whip_priority")
    search_fields = ("division",)
    autocomplete_fields = ("division",)


@admin.register(DivisionAnnotation)
class DivisionAnnotationAdmin(admin.ModelAdmin):
    list_display = ("id", "division", "detail", "link")
    search_fields = ("division",)
    autocomplete_fields = ("division",)


@admin.register(AgreementAnnotation)
class AgreementAnnotationAdmin(admin.ModelAdmin):
    list_display = ("id", "agreement", "detail", "link")
    search_fields = ("agreement",)
    autocomplete_fields = ("agreement",)


@admin.register(VoteAnnotation)
class VoteAnnotationAdmin(admin.ModelAdmin):
    list_display = ("id", "division", "person", "detail", "link")
    search_fields = ("division",)
    autocomplete_fields = ("division", "person")
