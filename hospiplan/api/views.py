from rest_framework import viewsets, status
from rest_framework.response import Response
from django.utils import timezone
from .models import *
from .serializers import *

# ── Pages HTML ────────────────────────────────────────────────
class StaffViewSet(viewsets.ModelViewSet):
    queryset         = Staff.objects.all()
    serializer_class = StaffSerializer

class ShiftViewSet(viewsets.ModelViewSet):
    queryset         = Shift.objects.all()
    serializer_class = ShiftSerializer

class AbsenceViewSet(viewsets.ModelViewSet):
    queryset         = Absence.objects.all()
    serializer_class = AbsenceSerializer

class CareUnitViewSet(viewsets.ModelViewSet):
    queryset         = CareUnit.objects.all()
    serializer_class = CareUnitSerializer

class ShiftTypeViewSet(viewsets.ModelViewSet):
    queryset         = ShiftType.objects.all()
    serializer_class = ShiftTypeSerializer

# ── Affectation avec contraintes dures ───────────────────────
class ShiftAssignmentViewSet(viewsets.ModelViewSet):
    queryset         = ShiftAssignment.objects.all()
    serializer_class = ShiftAssignmentSerializer

    def create(self, request, *args, **kwargs):
        staff_id = request.data.get('staff')
        shift_id = request.data.get('shift')

        try:
            staff = Staff.objects.get(id=staff_id)
            shift = Shift.objects.get(id=shift_id)
        except (Staff.DoesNotExist, Shift.DoesNotExist):
            return Response(
                {'detail': 'Soignant ou poste introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # ── Contrainte 1 : Soignant actif ─────────────────────
        if not staff.is_active:
            return Response(
                {'detail': '❌ Ce soignant est inactif.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Contrainte 2 : Soignant absent ────────────────────
        absence = Absence.objects.filter(
            staff=staff,
            start_date__lte=shift.start_datetime.date(),
            expected_end_date__gte=shift.start_datetime.date()
        ).first()
        if absence:
            return Response(
                {'detail': f'❌ Ce soignant est absent du {absence.start_date} au {absence.expected_end_date}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Contrainte 3 : Chevauchement de créneaux ──────────
        chevauchement = ShiftAssignment.objects.filter(
            staff=staff,
            shift__start_datetime__lt=shift.end_datetime,
            shift__end_datetime__gt=shift.start_datetime
        ).exclude(shift=shift).first()
        if chevauchement:
            return Response(
                {'detail': f'❌ Ce soignant est déjà affecté à un poste qui chevauche ce créneau.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Contrainte 4 : Certifications requises ────────────
        certifications_requises = shift.required_certifications.all()
        for certif in certifications_requises:
            possede = StaffCertification.objects.filter(
                staff=staff,
                certification=certif,
                expiration_date__gte=shift.start_datetime.date()
            ).first()
            if not possede:
                return Response(
                    {'detail': f'❌ Certification manquante ou expirée : {certif.name}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ── Contrainte 5 : Contrat autorise ce type de garde ──
        contrat = Contract.objects.filter(
            staff=staff,
            start_date__lte=shift.start_datetime.date()
        ).filter(
            models.Q(end_date__isnull=True) |
            models.Q(end_date__gte=shift.start_datetime.date())
        ).first()

        if contrat and shift.shift_type.requires_rest_after:
            if not contrat.contract_type.night_shift_allowed:
                return Response(
                    {'detail': '❌ Le contrat de ce soignant ne l\'autorise pas à faire des gardes de nuit.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ── Contrainte 6 : Quota heures hebdomadaires ─────────
        if contrat:
            debut_semaine = shift.start_datetime.date() - timezone.timedelta(
                days=shift.start_datetime.weekday()
            )
            fin_semaine = debut_semaine + timezone.timedelta(days=6)

            heures_semaine = sum([
                (a.shift.end_datetime - a.shift.start_datetime).seconds / 3600
                for a in ShiftAssignment.objects.filter(
                    staff=staff,
                    shift__start_datetime__date__gte=debut_semaine,
                    shift__start_datetime__date__lte=fin_semaine
                ).select_related('shift')
            ])
            duree_poste = (shift.end_datetime - shift.start_datetime).seconds / 3600

            if heures_semaine + duree_poste > contrat.contract_type.max_hours_per_week:
                return Response(
                    {'detail': f'❌ Quota hebdomadaire dépassé. Heures déjà planifiées : {heures_semaine}h / {contrat.contract_type.max_hours_per_week}h max.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ── Toutes les contraintes passées → on crée ──────────
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)