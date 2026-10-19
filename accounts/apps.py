from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts & Roles"

    def ready(self):
        # Ensure every user gets a Profile row automatically.
        from . import signals  # noqa: F401
