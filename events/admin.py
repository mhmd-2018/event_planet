from django.contrib import admin

from .models import Attribute, AttributeOption, Event, EventAttributeValue, Stage, StageRole


class StageInline(admin.TabularInline):
    model = Stage
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "owner", "status", "start_at", "capacity"]
    list_filter = ["status"]
    search_fields = ["title", "owner__username"]
    inlines = [StageInline]


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "order", "title", "start_at"]


@admin.register(StageRole)
class StageRoleAdmin(admin.ModelAdmin):
    list_display = ["id", "stage", "user", "role"]
    list_filter = ["role"]


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "key", "data_type", "required"]
    list_filter = ["data_type"]


@admin.register(AttributeOption)
class AttributeOptionAdmin(admin.ModelAdmin):
    list_display = ["id", "attribute", "value", "order"]


@admin.register(EventAttributeValue)
class EventAttributeValueAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "attribute"]
    list_filter = ["attribute__data_type"]
