"""Permissions DRF selon la matrice des rôles (CONTRATS §3.2)."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import ROLE_RANK


def _is_user(request):
    u = request.user
    return bool(u and getattr(u, "is_authenticated", False) and not getattr(u, "is_service", False))


class IsUserToken(BasePermission):
    """Jeton utilisateur obligatoire (un jeton de service est refusé)."""

    message = "Jeton utilisateur requis."
    code = "FORBIDDEN_ROLE"

    def has_permission(self, request, view):
        return _is_user(request)


def HasRole(*roles):
    """``HasRole("ADMIN", "SUPERADMIN")`` : l'un des rôles listés."""

    class _HasRole(BasePermission):
        message = f"Rôle requis : {', '.join(roles)}."
        code = "FORBIDDEN_ROLE"

        def has_permission(self, request, view):
            return _is_user(request) and request.user.role in roles

    _HasRole.__name__ = f"HasRole_{'_'.join(roles)}"
    return _HasRole


def MinRole(role, read_role=None):
    """Écriture réservée à ``role`` et au-dessus ; lecture à ``read_role`` et au-dessus.
    Ex. référentiels : ``MinRole("ADMIN", read_role="SOIGNANT")``."""
    read_role = read_role or role

    class _MinRole(BasePermission):
        message = f"Rôle minimum requis : {role}."
        code = "FORBIDDEN_ROLE"

        def has_permission(self, request, view):
            if not _is_user(request):
                return False
            needed = read_role if request.method in SAFE_METHODS else role
            return ROLE_RANK.get(request.user.role, -1) >= ROLE_RANK[needed]

    _MinRole.__name__ = f"MinRole_{role}"
    return _MinRole


def IsServiceToken(*scopes):
    """Jeton de service portant tous les ``scopes`` + en-tête X-Etablissement-Id
    (sauf si la vue définit ``allow_no_tenant = True``)."""

    class _IsServiceToken(BasePermission):
        message = "Jeton de service requis."
        code = "FORBIDDEN_ROLE"

        def has_permission(self, request, view):
            u = request.user
            if not (u and getattr(u, "is_service", False)):
                return False
            if not set(scopes).issubset(set(u.scope)):
                self.message = f"Scope requis : {', '.join(scopes)}."
                return False
            if u.etablissement_id is None and not getattr(view, "allow_no_tenant", False):
                self.message = "En-tête X-Etablissement-Id requis."
                return False
            return True

    _IsServiceToken.__name__ = f"IsServiceToken_{'_'.join(scopes)}"
    return _IsServiceToken
