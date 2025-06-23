# Register your models here.
from django.contrib import admin

from .models import (
    Agreement,
    AgreementAnnotation,
    AnalysisOverride,
    BulkAPIUser,
    Division,
    DivisionAnnotation,
    Person,
    Statement,
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


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = ("id", "chamber_slug", "date", "title", "type")
    list_filter = ("chamber_slug", "type", "date")
    search_fields = ("title", "key")
    date_hierarchy = "date"


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


@admin.register(BulkAPIUser)
class BulkAPIUserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "purpose",
        "access_count",
        "created_at",
        "last_accessed",
    )
    search_fields = ("email", "purpose")
    readonly_fields = ("token", "access_count")
    fields = (
        "email",
        "purpose",
        "token",
        "access_count",
        "created_at",
        "last_accessed",
    )
