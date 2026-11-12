"""Format d'erreur commun (CONTRATS §2) :
``{"error": {"code", "message", "details", "correlation_id"}}``

Réglage : ``REST_FRAMEWORK["EXCEPTION_HANDLER"] = "hospiplan_auth.errors.exception_handler"``
"""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .correlation import get_correlation_id

logger = logging.getLogger("hospiplan.errors")

_DEFAULT_CODES = [
    (exceptions.ValidationError, "VALIDATION_ERROR"),
    (exceptions.ParseError, "VALIDATION_ERROR"),
    (exceptions.UnsupportedMediaType, "VALIDATION_ERROR"),
    (exceptions.NotAuthenticated, "AUTH_REQUIRED"),
    (exceptions.AuthenticationFailed, "TOKEN_INVALID"),
    (exceptions.PermissionDenied, "FORBIDDEN_ROLE"),
    (exceptions.NotFound, "NOT_FOUND"),
    (exceptions.MethodNotAllowed, "METHOD_NOT_ALLOWED"),
    (exceptions.Throttled, "RATE_LIMITED"),
]
_KNOWN_CODES = {
    "TOKEN_EXPIRED", "TOKEN_INVALID", "AUTH_REQUIRED", "FORBIDDEN_ROLE", "FORBIDDEN_TENANT",
    "NOT_FOUND", "CONFLICT", "RATE_LIMITED", "VALIDATION_ERROR",
    "UPSTREAM_ERROR", "UPSTREAM_UNAVAILABLE", "UPSTREAM_TIMEOUT",
}


class ApiError(exceptions.APIException):
    """Erreur métier explicite :
    ``raise ApiError(400, "RULE_NO_OVERLAP", "Chevauchement…", details={"staff_id": 3})``."""

    def __init__(self, status_code, code, message, details=None):
        self.status_code = status_code
        self.error_code = code
        self.details = details or {}
        super().__init__(detail=message, code=code)


def error_response(status_code, code, message, details=None):
    return Response(
        {"error": {"code": code, "message": message, "details": details or {},
                   "correlation_id": get_correlation_id()}},
        status=status_code,
    )


def _first_message(detail):
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    if isinstance(detail, dict) and detail:
        key, val = next(iter(detail.items()))
        msg = _first_message(val)
        return msg if key in ("detail", "non_field_errors", "messages") else f"{key} : {msg}"
    return str(detail)


def _find_code(codes):
    """Cherche un code connu dans la structure renvoyée par ``exc.get_codes()``."""
    if isinstance(codes, str):
        return codes if codes in _KNOWN_CODES else None
    if isinstance(codes, dict):
        codes = list(codes.values())
    if isinstance(codes, list):
        for c in codes:
            found = _find_code(c)
            if found:
                return found
    return None


def exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, ApiError):
        return error_response(exc.status_code, exc.error_code, str(exc.detail), exc.details)

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Erreur non gérée", exc_info=exc)
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                              "Erreur interne du serveur.")

    code = _find_code(exc.get_codes()) if hasattr(exc, "get_codes") else None
    if code is None:
        code = next((c for cls, c in _DEFAULT_CODES if isinstance(exc, cls)), "ERROR")
    if code == "TOKEN_INVALID" and "expir" in str(exc.detail).lower():
        code = "TOKEN_EXPIRED"  # message de simplejwt « Token is expired »

    details = exc.detail if isinstance(exc, exceptions.ValidationError) else {}
    resp = error_response(response.status_code, code, _first_message(exc.detail), details)
    for header in ("WWW-Authenticate", "Retry-After"):
        if header in response:
            resp[header] = response[header]
    return resp
