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

urlpatterns = [
    path('api/', include(router.urls)),
]