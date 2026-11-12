import os

from django.db import connection
from django.http import JsonResponse

from .conf import auth_setting


def health(request):
    """GET /health — sans authentification (sonde App Service et alertes).
    200 si la base répond, 503 sinon."""
    db_ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:  # noqa: BLE001 — on veut un statut, pas une trace
        db_ok = False
    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "service": auth_setting("SERVICE_NAME"),
            "version": os.environ.get("GIT_SHA", "dev"),
            "database": "ok" if db_ok else "unreachable",
        },
        status=200 if db_ok else 503,
    )
