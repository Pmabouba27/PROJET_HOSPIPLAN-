"""Émission des jetons (CONTRATS §3)."""
import json
import uuid
from datetime import datetime, timezone

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework_simplejwt.tokens import RefreshToken


def user_claims(user):
    return {
        "email": user.email,
        "etablissement_id": user.etablissement_id,
        "role": user.role,
        "staff_id": user.staff_id,
    }


def tokens_for(user):
    """Paire access/refresh. Les claims métier sont recopiés dans l'access token
    par simplejwt ; ils sont relus depuis la base à chaque refresh."""
    refresh = RefreshToken.for_user(user)
    for key, value in user_claims(user).items():
        refresh[key] = value
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def service_clients():
    try:
        clients = json.loads(settings.SERVICE_CLIENTS_JSON or "{}")
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured("SERVICE_CLIENTS n'est pas un JSON valide.") from exc
    if not isinstance(clients, dict):
        raise ImproperlyConfigured("SERVICE_CLIENTS doit être un objet JSON.")
    return clients


def service_token(client_id, scope):
    now = datetime.now(timezone.utc)
    lifetime = settings.SERVICE_TOKEN_LIFETIME
    payload = {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE_INTERNAL,
        "sub": client_id,
        "type": "service",
        "scope": list(scope),
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm="RS256"), int(lifetime.total_seconds())
