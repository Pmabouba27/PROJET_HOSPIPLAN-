import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DEFAULTS = {
    "PUBLIC_KEY": None,
    "ISSUER": "hospiplan-identite",
    "AUDIENCE_API": "hospiplan-api",
    "AUDIENCE_INTERNAL": "hospiplan-internal",
    "SERVICE_NAME": "service-inconnu",
    "LEEWAY_SECONDS": 10,
}


def auth_setting(name):
    value = getattr(settings, "HOSPIPLAN_AUTH", {}).get(name, DEFAULTS[name])
    if name == "PUBLIC_KEY" and not value:
        raise ImproperlyConfigured(
            "HOSPIPLAN_AUTH['PUBLIC_KEY'] manquant (variable JWT_PUBLIC_KEY ou JWT_PUBLIC_KEY_FILE)"
        )
    return value


def load_pem(env_name, base_dir=None):
    r"""Lit une clé PEM depuis ``<env_name>`` (contenu ; ``\n`` échappés acceptés,
    pratique pour les Paramètres d'application Azure) ou depuis ``<env_name>_FILE``
    (chemin d'un fichier, relatif à ``base_dir`` s'il n'est pas absolu).
    Renvoie None si la clé n'est pas configurée ou si le fichier n'existe pas
    (le service décide alors de l'erreur à lever)."""
    raw = os.environ.get(env_name)
    if raw:
        return raw.replace("\\n", "\n").strip() + "\n"
    path = os.environ.get(f"{env_name}_FILE")
    if not path:
        return None
    path = Path(path)
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path
    return path.read_text(encoding="utf-8") if path.is_file() else None
