from django.contrib import admin

from .models import Feedback, Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "participant", "status", "registered_at"]
    list_filter = ["status"]
    search_fields = ["event__title", "participant__username"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "participant", "rating", "created_at"]
    search_fields = ["event__title", "participant__username"]
