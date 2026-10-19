from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Profile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ["id", "username", "email", "role", "is_active", "is_superuser"]
    list_filter = ["role", "is_superuser", "is_active"]
    fieldsets = DjangoUserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (("Role", {"fields": ("role",)}),)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "full_name", "website"]
    search_fields = ["user__username", "full_name"]
