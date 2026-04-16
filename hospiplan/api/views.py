from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from django.utils import timezone
from django.db import models, transaction
from django.core.exceptions import ValidationError
from datetime import datetime
from .models import *
from .serializers import *
from .planning.generator import generate_daily_planning
from .planning.metaheuristic import tabu_search

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

class CertificationViewSet(viewsets.ModelViewSet):
    queryset         = Certification.objects.all()
    serializer_class = CertificationSerializer

class AbsenceTypeViewSet(viewsets.ModelViewSet):
    queryset         = AbsenceType.objects.all()
    serializer_class = AbsenceTypeSerializer

class PreferenceViewSet(viewsets.ModelViewSet):
    queryset         = Preference.objects.all()
    serializer_class = PreferenceSerializer

class ServiceViewSet(viewsets.ModelViewSet):
    queryset         = Service.objects.all()
    serializer_class = ServiceSerializer

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
                {'detail': '❌ Ce soignant est déjà affecté à un poste qui chevauche ce créneau.'},
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

        if contrat and shift.shift_type.is_night_shift:
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
                    {'detail': f'❌ Quota hebdomadaire dépassé. Heures planifiées : {heures_semaine}h / {contrat.contract_type.max_hours_per_week}h max.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ── Contrainte 7 : Contraintes impératives ────────────
        contraintes = Preference.objects.filter(
            staff=staff,
            is_hard_constraint=True,
            start_date__lte=shift.start_datetime.date()
        ).filter(
            models.Q(end_date__isnull=True) |
            models.Q(end_date__gte=shift.start_datetime.date())
        )
        for contrainte in contraintes:
            jour_garde = shift.start_datetime.strftime('%A').lower()
            if jour_garde in contrainte.description.lower():
                return Response(
                    {'detail': f'❌ Contrainte impérative : {contrainte.description}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ── Toutes les contraintes passées → on crée ──────────
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        assignment  = self.get_object()
        shift       = assignment.shift
        nb_affectes = ShiftAssignment.objects.filter(shift=shift).count()

        if nb_affectes <= shift.min_staff:
            return Response(
                {'detail': f'❌ Impossible de supprimer — effectif minimum requis : {shift.min_staff} soignant(s).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        assignment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 — génération automatique de planning
# ─────────────────────────────────────────────────────────────────────────

class GeneratePlanningView(APIView):
    """
    POST /api/plannings/generate/
    Body JSON :
      {
        "date":       "YYYY-MM-DD",   # jour à planifier
        "service_id": 3,               # optionnel : limite à un service
        "metaheuristic": true,         # optionnel : active la recherche tabou
        "persist":    true             # optionnel : sauvegarde en BD (défaut true)
      }

    Réponse :
      {
        "assignments":  [{shift, staff, legal}, ...],
        "uncovered":    [{shift, missing, reason}, ...],
        "score":        { total, details{M1..M7}, weights },
        "summary":      { shifts_total, covered, uncovered, staff_used },
        "persisted":    n   # nombre d'affectations réellement écrites
      }
    """

    def post(self, request, *args, **kwargs):
        raw_date = request.data.get('date')
        service_id = request.data.get('service_id')
        use_meta = bool(request.data.get('metaheuristic', True))
        persist = bool(request.data.get('persist', True))

        if not raw_date:
            return Response({'detail': 'Champ "date" requis (YYYY-MM-DD).'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            target = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': 'Date invalide, format attendu YYYY-MM-DD.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # 1. Heuristique gloutonne
        result = generate_daily_planning(target, service_id=service_id)

        # 2. Métaheuristique optionnelle (toujours sous contrôle des dures)
        meta_info = None
        if use_meta and result['assignments']:
            meta_info = tabu_search(
                result['_ctx'], result['_aux'], result['_weights'],
                max_iter=200, tabu_len=25, time_limit_s=6.0,
            )
            # Recalcule les affectations finales depuis ctx
            final = []
            for staff_id, lst in result['_ctx'].assignments_by_staff.items():
                for (_, _, shift_id, _) in lst:
                    if shift_id in result['_ctx'].shifts:
                        # Ne garde que ce qui est dans la fenêtre
                        final.append({'shift': shift_id, 'staff': staff_id, 'legal': True})
            # Filtre pour ne garder que les affectations « nouvelles » (celles
            # pas déjà présentes en base avant la génération).
            from api.models import ShiftAssignment as _SA
            existing_keys = set(
                _SA.objects.filter(shift_id__in=list(result['_ctx'].shifts.keys()))
                .values_list('staff_id', 'shift_id')
            )
            result['assignments'] = [
                a for a in final if (a['staff'], a['shift']) not in existing_keys
            ]
            # Recalcul du score final
            from .planning.scoring import total_score
            result['score'] = total_score(
                result['_ctx'], result['_aux'], result['_weights']
            )

        # 3. Persistance : on passe par save() => full_clean() => dures revérifiées
        persisted = 0
        errors = []
        if persist:
            with transaction.atomic():
                for a in result['assignments']:
                    try:
                        sa = ShiftAssignment(staff_id=a['staff'], shift_id=a['shift'])
                        sa.save()
                        persisted += 1
                    except ValidationError as ve:
                        # Filet de sécurité : si la BD refuse (concurrent change etc.),
                        # on n'enregistre pas mais on ne plante pas la réponse.
                        errors.append({'shift': a['shift'], 'staff': a['staff'],
                                       'detail': str(ve)})

        return Response({
            'date': raw_date,
            'service_id': service_id,
            'assignments': result['assignments'],
            'uncovered': result['uncovered'],
            'score': result['score'],
            'summary': result['summary'],
            'metaheuristic': meta_info,
            'persisted': persisted,
            'errors': errors,
        }, status=status.HTTP_200_OK)