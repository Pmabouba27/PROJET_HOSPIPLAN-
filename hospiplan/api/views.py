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
    queryset         = Staff.objects.all().prefetch_related('roles', 'specialties')
    serializer_class = StaffSerializer


class StaffProfileView(APIView):
    """
    GET /api/staff/{id}/profile/
    Retourne la fiche complète d'un soignant :
      - informations de base
      - rôles et spécialités
      - contrat actif + historique contrats
      - certifications (avec statut valide/expiré)
      - absences (avec statut actif/passé)
      - préférences et contraintes déclarées
    """
    def get(self, request, pk, *args, **kwargs):
        try:
            staff = Staff.objects.prefetch_related(
                'roles', 'specialties',
                'contracts__contract_type',
                'certifications__certification',
                'absences__absence_type',
                'preferences__target_shift_type',
                'preferences__target_service',
            ).get(pk=pk)
        except Staff.DoesNotExist:
            return Response({'detail': 'Soignant introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StaffProfileSerializer(staff)
        return Response(serializer.data)


class StaffListWithStatusView(APIView):
    """
    GET /api/staff/overview/
    Retourne tous les soignants avec leur statut d'absence du jour,
    leur contrat actif et le nombre d'absences/préférences.
    Conçu pour l'affichage en cards sur la page soignants.
    """
    def get(self, request, *args, **kwargs):
        from django.utils import timezone
        from django.db.models import Count, Q

        today = timezone.now().date()

        staff_qs = Staff.objects.prefetch_related(
            'roles', 'specialties',
            'contracts__contract_type',
            'absences',
            'preferences',
        ).all()

        result = []
        for s in staff_qs:
            # Absence active aujourd'hui
            absence_active = s.absences.filter(
                start_date__lte=today,
                expected_end_date__gte=today
            ).select_related('absence_type').first()

            # Contrat actif
            from django.db.models import Q as Qm
            contrat = s.contracts.filter(
                start_date__lte=today
            ).filter(
                Qm(end_date__isnull=True) | Qm(end_date__gte=today)
            ).select_related('contract_type').first()

            result.append({
                'id':           s.id,
                'first_name':   s.first_name,
                'last_name':    s.last_name,
                'email':        s.email,
                'phone':        s.phone,
                'is_active':    s.is_active,
                'roles':        [{'id': r.id, 'name': r.name} for r in s.roles.all()],
                'specialties':  [{'id': sp.id, 'name': sp.name} for sp in s.specialties.all()],
                'is_absent_today': absence_active is not None,
                'absence_today': {
                    'type': absence_active.absence_type.name,
                    'start': str(absence_active.start_date),
                    'end':   str(absence_active.expected_end_date),
                } if absence_active else None,
                'active_contract': {
                    'type_name':           contrat.contract_type.name,
                    'max_hours_per_week':  contrat.contract_type.max_hours_per_week,
                    'night_shift_allowed': contrat.contract_type.night_shift_allowed,
                    'workload_percent':    contrat.workload_percent,
                } if contrat else None,
                'nb_absences':    s.absences.count(),
                'nb_preferences': s.preferences.count(),
            })

        return Response(result)

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


# ─────────────────────────────────────────────────────────────────────────
# Statistiques — tableau de bord
# ─────────────────────────────────────────────────────────────────────────

class StatsView(APIView):
    """
    GET /api/stats/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

    Renvoie un tableau de bord complet sur la période :
      - par soignant : shifts effectués, services, types de garde
      - par service  : couverture des créneaux
      - global       : taux de couverture, répartition nuits/jours
    """

    def get(self, request, *args, **kwargs):
        from datetime import date as _date
        from django.db.models import Count, Q

        raw_start = request.query_params.get('start_date')
        raw_end   = request.query_params.get('end_date')

        if not raw_start or not raw_end:
            return Response(
                {'detail': 'Paramètres start_date et end_date requis (YYYY-MM-DD).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            start = datetime.strptime(raw_start, '%Y-%m-%d').date()
            end   = datetime.strptime(raw_end,   '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': 'Format de date invalide (YYYY-MM-DD attendu).'},
                            status=status.HTTP_400_BAD_REQUEST)

        if start > end:
            return Response({'detail': 'start_date doit être ≤ end_date.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # ── Affectations sur la période ────────────────────────────────────
        assignments = (
            ShiftAssignment.objects
            .filter(
                shift__start_datetime__date__gte=start,
                shift__start_datetime__date__lte=end,
            )
            .select_related('staff', 'shift', 'shift__shift_type',
                            'shift__care_unit', 'shift__care_unit__service')
        )

        # ── Shifts disponibles sur la période ─────────────────────────────
        shifts_qs = (
            Shift.objects
            .filter(
                start_datetime__date__gte=start,
                start_datetime__date__lte=end,
            )
            .select_related('care_unit', 'care_unit__service', 'shift_type')
        )

        total_shifts        = shifts_qs.count()
        shifts_with_assign  = shifts_qs.filter(assignments__isnull=False).distinct().count()
        coverage_rate       = round(shifts_with_assign / total_shifts * 100, 1) if total_shifts else 0

        # ── Stats par soignant ─────────────────────────────────────────────
        staff_stats = {}
        for a in assignments:
            sid = a.staff_id
            if sid not in staff_stats:
                staff_stats[sid] = {
                    'id':        sid,
                    'name':      f'{a.staff.first_name} {a.staff.last_name}',
                    'total':     0,
                    'nights':    0,
                    'weekends':  0,
                    'services':  set(),
                }
            staff_stats[sid]['total'] += 1
            if a.shift.shift_type.is_night_shift:
                staff_stats[sid]['nights'] += 1
            wd = a.shift.start_datetime.weekday()
            if wd >= 5:
                staff_stats[sid]['weekends'] += 1
            staff_stats[sid]['services'].add(a.shift.care_unit.service.name)

        staff_list = []
        for v in staff_stats.values():
            v['services'] = list(v['services'])
            staff_list.append(v)
        staff_list.sort(key=lambda x: -x['total'])

        # ── Stats par service ──────────────────────────────────────────────
        service_stats = {}
        for sh in shifts_qs:
            sname = sh.care_unit.service.name
            if sname not in service_stats:
                service_stats[sname] = {'name': sname, 'total_shifts': 0, 'covered': 0}
            service_stats[sname]['total_shifts'] += 1

        for a in assignments:
            sname = a.shift.care_unit.service.name
            if sname in service_stats:
                service_stats[sname]['covered'] += 1

        services_list = []
        for v in service_stats.values():
            v['coverage_pct'] = round(v['covered'] / v['total_shifts'] * 100, 1) if v['total_shifts'] else 0
            services_list.append(v)
        services_list.sort(key=lambda x: x['name'])

        # ── Répartition par type de garde ─────────────────────────────────
        type_stats = {}
        for a in assignments:
            t = a.shift.shift_type.name
            type_stats[t] = type_stats.get(t, 0) + 1

        # ── Absences sur la période ────────────────────────────────────────
        absences_count = (
            Absence.objects
            .filter(start_date__lte=end, expected_end_date__gte=start)
            .count()
        )

        return Response({
            'period': {'start': raw_start, 'end': raw_end},
            'global': {
                'total_shifts':       total_shifts,
                'shifts_covered':     shifts_with_assign,
                'coverage_rate_pct':  coverage_rate,
                'total_assignments':  assignments.count(),
                'absences_count':     absences_count,
            },
            'by_staff':   staff_list,
            'by_service': services_list,
            'by_type':    [{'type': k, 'count': v} for k, v in type_stats.items()],
        }, status=status.HTTP_200_OK)