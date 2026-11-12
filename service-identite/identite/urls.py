from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from comptes import views
from hospiplan_auth.health import health

class OptionalSlashRouter(DefaultRouter):
    """Accepte /api/v1/users et /api/v1/users/ (contrat sans slash final)."""

    include_root_view = False
    include_format_suffixes = False

    def __init__(self):
        super().__init__()
        self.trailing_slash = "/?"


router = OptionalSlashRouter()
router.register(r"etablissements", views.EtablissementViewSet, basename="etablissement")
router.register(r"users", views.UtilisateurViewSet, basename="user")

urlpatterns = [
    re_path(r"^health/?$", health, name="health"),
    re_path(r"^api/v1/auth/login/?$", views.LoginView.as_view(), name="login"),
    re_path(r"^api/v1/auth/refresh/?$", views.RefreshView.as_view(), name="refresh"),
    re_path(r"^api/v1/auth/logout/?$", views.LogoutView.as_view(), name="logout"),
    re_path(r"^api/v1/auth/me/?$", views.MeView.as_view(), name="me"),
    re_path(r"^api/v1/auth/jwks/?$", views.JwksView.as_view(), name="jwks"),
    re_path(r"^internal/v1/auth/service-token/?$", views.ServiceTokenView.as_view(), name="service-token"),
    path("api/v1/", include(router.urls)),
]
