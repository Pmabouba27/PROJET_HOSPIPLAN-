"""Isolation multi-établissement : chaque requête est filtrée par
l'etablissement_id du jeton, jamais par un paramètre envoyé par le client."""
from rest_framework.exceptions import PermissionDenied


class TenantQuerysetMixin:
    tenant_field = "etablissement_id"

    def get_tenant_id(self):
        user = self.request.user
        if getattr(user, "role", None) == "SUPERADMIN" and not getattr(user, "is_service", False):
            return None  # l'éditeur SaaS voit tous les établissements
        tenant = getattr(user, "etablissement_id", None)
        if tenant is None:
            raise PermissionDenied("Aucun établissement associé au jeton.", code="FORBIDDEN_TENANT")
        return tenant

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = self.get_tenant_id()
        return qs if tenant is None else qs.filter(**{self.tenant_field: tenant})

    def perform_create(self, serializer):
        tenant = self.get_tenant_id()
        if tenant is None:
            serializer.save()  # SUPERADMIN : établissement fourni explicitement
        else:
            serializer.save(**{self.tenant_field: tenant})
