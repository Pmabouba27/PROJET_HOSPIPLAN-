from django.apps import AppConfig
from django.conf import settings


class ComptesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comptes"
    verbose_name = "Comptes et établissements"

    def ready(self):
        from hospiplan_auth.db import connect_schema_creation

        connect_schema_creation(settings.DB_SCHEMA)
