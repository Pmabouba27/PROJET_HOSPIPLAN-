"""Endpoints de service-identite (CONTRATS §4)."""
import hmac
import logging

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from jwt.algorithms import RSAAlgorithm
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from hospiplan_auth.errors import ApiError
from hospiplan_auth.permissions import HasRole, MinRole
from hospiplan_auth.tenant import TenantQuerysetMixin

from .models import Etablissement, Utilisateur
from .serializers import (EtablissementSerializer, LoginSerializer, RefreshSerializer,
                          ServiceTokenSerializer, UtilisateurSerializer)
from .tokens import service_clients, service_token, tokens_for

security_log = logging.getLogger("hospiplan.security")
Role = Utilisateur.Role


def _check_can_login(user):
    if not user.is_active:
        raise ApiError(401, "INVALID_CREDENTIALS", "Email ou mot de passe incorrect.")
    if user.role != Role.SUPERADMIN and not user.etablissement.est_actif:
        raise ApiError(403, "ETABLISSEMENT_SUSPENDU",
                       "L'abonnement de votre établissement n'est pas actif.",
                       {"statut_abonnement": user.etablissement.statut_abonnement})


# --------------------------------------------------------------------- auth
class LoginView(APIView):
    """POST /api/v1/auth/login — limité à 5 essais / min / IP."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["email"].lower()
        user = authenticate(request, email=email, password=data.validated_data["password"])
        if user is None:
            # Même message que pour un compte inexistant (pas d'énumération des comptes)
            security_log.warning("Échec de connexion email=%s ip=%s", email, request.META.get("REMOTE_ADDR"))
            raise ApiError(401, "INVALID_CREDENTIALS", "Email ou mot de passe incorrect.")
        _check_can_login(user)
        security_log.info("Connexion user=%s role=%s etab=%s", user.pk, user.role, user.etablissement_id)
        return Response({**tokens_for(user), "user": UtilisateurSerializer(user).data})


class RefreshView(APIView):
    """POST /api/v1/auth/refresh — rotation : l'ancien refresh est révoqué et les
    claims (rôle, établissement) sont relus en base."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        data = RefreshSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            old = RefreshToken(data.validated_data["refresh"])  # signature, expiration, liste noire
        except TokenError:
            raise ApiError(401, "TOKEN_INVALID", "Refresh token invalide, expiré ou révoqué.")
        user = Utilisateur.objects.select_related("etablissement").filter(
            pk=old[settings.SIMPLE_JWT["USER_ID_CLAIM"]]).first()
        if user is None:
            raise ApiError(401, "TOKEN_INVALID", "Refresh token invalide, expiré ou révoqué.")
        _check_can_login(user)
        with transaction.atomic():
            old.blacklist()
            return Response(tokens_for(user))


class LogoutView(APIView):
    """POST /api/v1/auth/logout — révoque le refresh token."""

    def post(self, request):
        data = RefreshSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            token = RefreshToken(data.validated_data["refresh"])
        except TokenError:
            return Response(status=status.HTTP_204_NO_CONTENT)  # déjà invalide : rien à faire
        if str(token[settings.SIMPLE_JWT["USER_ID_CLAIM"]]) != str(request.user.id):
            raise ApiError(403, "FORBIDDEN_ROLE", "Ce refresh token appartient à un autre utilisateur.")
        token.blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/v1/auth/me"""

    def get(self, request):
        user = Utilisateur.objects.filter(pk=request.user.id, is_active=True).first()
        if user is None:
            raise ApiError(401, "TOKEN_INVALID", "Compte introuvable ou désactivé.")
        return Response(UtilisateurSerializer(user).data)


class JwksView(APIView):
    """GET /api/v1/auth/jwks — clé publique de vérification (format JWKS)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        key = RSAAlgorithm.to_jwk(load_pem_public_key(settings.JWT_PUBLIC_KEY.encode()), as_dict=True)
        key.update({"use": "sig", "alg": "RS256"})
        return Response({"keys": [key]})


# ---------------------------------------------------------- établissements
class EtablissementViewSet(viewsets.ModelViewSet):
    """SUPERADMIN : gestion complète. ADMIN : lecture de son établissement.
    DELETE = résiliation (statut RESILIE), les données sont conservées."""

    serializer_class = EtablissementSerializer
    queryset = Etablissement.objects.all()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [HasRole(Role.SUPERADMIN, Role.ADMIN)()]
        return [HasRole(Role.SUPERADMIN)()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == Role.SUPERADMIN:
            return qs
        return qs.filter(pk=self.request.user.etablissement_id)

    def perform_destroy(self, instance):
        instance.statut_abonnement = Etablissement.Statut.RESILIE
        instance.save(update_fields=["statut_abonnement"])
        _revoke_tokens(Utilisateur.objects.filter(etablissement=instance))


# ------------------------------------------------------------ utilisateurs
class UtilisateurViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    """ADMIN : utilisateurs de son établissement. SUPERADMIN : tous.
    DELETE = désactivation + révocation des refresh tokens."""

    serializer_class = UtilisateurSerializer
    queryset = Utilisateur.objects.select_related("etablissement").all()
    permission_classes = [MinRole(Role.ADMIN)]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        etab = self.request.query_params.get("etablissement_id")
        if self.request.user.role == Role.SUPERADMIN and etab and etab.isdigit():
            qs = qs.filter(etablissement_id=int(etab))
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == Role.SUPERADMIN:
            serializer.save()
        else:
            serializer.save(etablissement_id=user.etablissement_id)

    def perform_update(self, serializer):
        serializer.save()
        if "password" in self.request.data or "role" in self.request.data:
            _revoke_tokens([serializer.instance])  # force une reconnexion

    def destroy(self, request, *args, **kwargs):
        target = self.get_object()
        if target.pk == request.user.id:
            raise ApiError(400, "VALIDATION_ERROR", "Vous ne pouvez pas désactiver votre propre compte.")
        target.is_active = False
        target.save(update_fields=["is_active"])
        _revoke_tokens([target])
        security_log.info("Désactivation user=%s par user=%s", target.pk, request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _revoke_tokens(users):
    for token in OutstandingToken.objects.filter(user__in=users):
        BlacklistedToken.objects.get_or_create(token=token)


# ------------------------------------------------------- jetons de service
class ServiceTokenView(APIView):
    """POST /internal/v1/auth/service-token — client_credentials pour les appels
    inter-services (CONTRATS §3.3)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "service_token"

    def post(self, request):
        data = ServiceTokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        client_id = data.validated_data["client_id"]
        client = service_clients().get(client_id)
        secret_ok = bool(client) and hmac.compare_digest(
            str(client.get("secret", "")).encode(), data.validated_data["client_secret"].encode())
        if not secret_ok or not client.get("secret"):
            security_log.warning("Jeton de service refusé client_id=%s", client_id)
            raise ApiError(401, "INVALID_CREDENTIALS", "Identifiants de service invalides.")
        token, expires_in = service_token(client_id, client.get("scope", []))
        return Response({"access": token, "token_type": "Bearer", "expires_in": expires_in})

