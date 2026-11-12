"""X-Correlation-ID (lu ou généré, renvoyé et ajouté aux logs) et journal des accès."""
import contextvars
import logging
import re
import time
import uuid

_correlation_id = contextvars.ContextVar("correlation_id", default="-")
_VALID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def get_correlation_id():
    return _correlation_id.get()


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_CORRELATION_ID", "")
        cid = incoming if _VALID.match(incoming) else str(uuid.uuid4())
        token = _correlation_id.set(cid)
        request.correlation_id = cid
        try:
            response = self.get_response(request)
            response["X-Correlation-ID"] = cid
            return response
        finally:
            _correlation_id.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Ajoute ``%(correlation_id)s`` aux enregistrements de log."""

    def filter(self, record):
        record.correlation_id = get_correlation_id()
        return True


class AccessLogMiddleware:
    """Journalisation des accès (exigence sécurité du TP) : méthode, chemin, statut,
    durée, utilisateur, établissement. Jamais le corps de la requête ni le jeton."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("hospiplan.access")

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        user = getattr(request, "user", None)
        authenticated = getattr(user, "is_authenticated", False)
        self.logger.info(
            "%s %s %s %.0fms user=%s etab=%s",
            request.method,
            request.path,
            response.status_code,
            (time.monotonic() - start) * 1000,
            getattr(user, "sub_label", getattr(user, "pk", "-")) if authenticated else "anonyme",
            getattr(user, "etablissement_id", "-") if authenticated else "-",
        )
        return response
