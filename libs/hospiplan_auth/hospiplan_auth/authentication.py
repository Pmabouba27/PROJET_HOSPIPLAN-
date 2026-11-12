"""Authentification DRF sans base de données : le JWT (RS256) émis par
service-identite est vérifié avec la clé publique, et l'utilisateur est
reconstruit à partir des claims (aucune requête SQL)."""
import jwt
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .conf import auth_setting


class ClaimsUser:
    """Utilisateur « léger » porté par le jeton."""

    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_staff = False
    is_superuser = False

    def __init__(self, claims):
        self.claims = claims
        self.token_type = claims.get("type")
        self.is_service = self.token_type == "service"
        sub = claims.get("sub")
        if not self.is_service and sub is not None and str(sub).isdigit():
            self.id = self.pk = int(sub)
        else:
            self.id = self.pk = sub
        self.email = claims.get("email")
        self.role = claims.get("role")
        self.etablissement_id = claims.get("etablissement_id")
        self.staff_id = claims.get("staff_id")
        self.scope = claims.get("scope") or []

    @property
    def sub_label(self):
        return f"service:{self.id}" if self.is_service else f"user:{self.id}"

    def __str__(self):
        return self.sub_label


def decode_token(token):
    """Vérifie signature, expiration, émetteur et audience. Accepte uniquement
    un jeton ``access`` (audience API) ou ``service`` (audience interne)."""
    try:
        claims = jwt.decode(
            token,
            auth_setting("PUBLIC_KEY"),
            algorithms=["RS256"],
            audience=[auth_setting("AUDIENCE_API"), auth_setting("AUDIENCE_INTERNAL")],
            issuer=auth_setting("ISSUER"),
            leeway=auth_setting("LEEWAY_SECONDS"),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed("Jeton expiré.", code="TOKEN_EXPIRED")
    except jwt.PyJWTError:
        raise exceptions.AuthenticationFailed("Jeton invalide.", code="TOKEN_INVALID")

    token_type = claims.get("type")
    aud = claims.get("aud")
    aud = aud if isinstance(aud, list) else [aud]
    if token_type == "access" and auth_setting("AUDIENCE_API") in aud:
        return claims
    if token_type == "service" and auth_setting("AUDIENCE_INTERNAL") in aud:
        return claims
    raise exceptions.AuthenticationFailed("Type de jeton non accepté.", code="TOKEN_INVALID")


class JWTClaimsAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("En-tête Authorization invalide.", code="TOKEN_INVALID")
        claims = decode_token(header[1].decode("utf-8", errors="ignore"))
        user = ClaimsUser(claims)
        # X-Etablissement-Id n'est pris en compte qu'avec un jeton de service (CONTRATS §3.3)
        if user.is_service:
            raw = request.META.get("HTTP_X_ETABLISSEMENT_ID", "")
            user.etablissement_id = int(raw) if raw.isdigit() else None
        return user, claims

    def authenticate_header(self, request):
        return self.keyword
