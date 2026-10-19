from django.contrib import admin

from .models import Result


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "participant", "team_name", "rank", "score", "publish_at"]
    search_fields = ["event__title", "participant__username", "team_name"]
