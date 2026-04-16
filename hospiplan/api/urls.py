from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'staff',        views.StaffViewSet)
router.register(r'shifts',       views.ShiftViewSet)
router.register(r'absences',     views.AbsenceViewSet)
router.register(r'assignments',  views.ShiftAssignmentViewSet)
router.register(r'care_units',   views.CareUnitViewSet)
router.register(r'shift_types',  views.ShiftTypeViewSet)
router.register(r'certifications', views.CertificationViewSet)
router.register(r'absence_types', views.AbsenceTypeViewSet)
router.register(r'preferences',   views.PreferenceViewSet)
router.register(r'services',      views.ServiceViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    # Phase 3 — génération automatique de planning
    path('api/plannings/generate/', views.GeneratePlanningView.as_view(),
         name='generate-planning'),
]