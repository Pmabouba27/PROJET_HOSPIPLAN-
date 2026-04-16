"""
Heuristique gloutonne constructive - Phase 3.

Idée générale :
  1. Ordonner les shifts à remplir par difficulté croissante (MRV - Most
     Restricted Variable) : shifts avec le moins de candidats légaux en
     premier, car si on les laisse pour la fin ils risquent d'être
     impossibles à couvrir.
  2. Pour chaque shift, pour chaque slot (min_staff à max_staff), choisir
     parmi les soignants légaux celui qui **minimise localement** le score
     soft si on l'affecte. En cas d'égalité, `least-loaded` : celui qui a le
     moins de gardes dans ce service (heuristique classique qui répond
     directement à M3).
  3. Si aucun soignant légal ne couvre un slot, on le laisse **non pourvu**
     et on le signale au frontend (conformément au cahier des charges).

Le générateur ne viole jamais une contrainte dure : chaque affectation
candidate est validée par l'oracle in-memory `FeasibilityContext.is_assignment_legal()`.
"""

from datetime import date, timedelta

from .feasibility import FeasibilityContext
from . import scoring


# ──────────────────────────────── Pré-chargement auxiliaire ──────────────

def _load_aux_data(window_start, window_end):
    """
    Charge en mémoire les données auxiliaires nécessaires au scoring
    (préférences, rôles, historique de services, prêts, services continuité).
    """
    from api.models import (
        Staff, Preference, StaffServiceAssignment, StaffLoan, Service,
    )

    all_staff_ids = list(Staff.objects.filter(is_active=True).values_list('id', flat=True))

    preferences_by_staff = {sid: [] for sid in all_staff_ids}
    for p in Preference.objects.all():
        preferences_by_staff.setdefault(p.staff_id, []).append({
            'kind': p.kind,
            'importance': p.importance or 1,
            'target_shift_type_id': p.target_shift_type_id,
            'target_service_id': p.target_service_id,
            'target_day_of_week': p.target_day_of_week,
            'start_date': p.start_date,
            'end_date': p.end_date,
        })

    role_by_staff = {sid: [] for sid in all_staff_ids}
    for s in Staff.objects.prefetch_related('roles'):
        role_by_staff[s.id] = [r.id for r in s.roles.all()]

    staff_service_history = {sid: set() for sid in all_staff_ids}
    for ssa in StaffServiceAssignment.objects.all():
        # Considéré « connu » si l'assignation a commencé avant la fenêtre
        if ssa.start_date < window_start:
            staff_service_history.setdefault(ssa.staff_id, set()).add(ssa.service_id)

    staff_loans = {sid: [] for sid in all_staff_ids}
    for loan in StaffLoan.objects.all():
        staff_loans.setdefault(loan.staff_id, []).append(
            (loan.from_service_id, loan.to_service_id, loan.start_date, loan.end_date)
        )

    services_requiring_continuity = set(
        Service.objects.filter(requires_care_continuity=True).values_list('id', flat=True)
    )

    # Trimestre courant : on considère le trimestre civil contenant window_start
    month = window_start.month
    q_start_month = ((month - 1) // 3) * 3 + 1
    trimester_start = date(window_start.year, q_start_month, 1)
    # Fin de trimestre = début du trimestre suivant - 1 jour
    next_q_month = q_start_month + 3
    next_q_year = window_start.year + (next_q_month - 1) // 12
    next_q_month = ((next_q_month - 1) % 12) + 1
    trimester_end = date(next_q_year, next_q_month, 1) - timedelta(days=1)

    return {
        'preferences_by_staff': preferences_by_staff,
        'role_by_staff': role_by_staff,
        'all_staff_ids': all_staff_ids,
        'staff_service_history': staff_service_history,
        'staff_loans': staff_loans,
        'services_requiring_continuity': services_requiring_continuity,
        'window_start': window_start,
        'window_end': window_end,
        'trimester_start': trimester_start,
        'trimester_end': trimester_end,
    }


# ──────────────────────────────── Comptage gardes par (staff, service) ───

def _shifts_per_staff_in_service(ctx, service_id):
    counts = {}
    for staff_id, lst in ctx.assignments_by_staff.items():
        n = 0
        for (_, _, sid, _) in lst:
            if sid in ctx.shifts and ctx.shifts[sid]['service_id'] == service_id:
                n += 1
        if n > 0:
            counts[staff_id] = n
    return counts


# ──────────────────────────────── Scoring incrémental local ──────────────

def _local_delta_score(ctx, aux, weights, staff_id, shift_id):
    """
    Évalue le score total **après** affectation temporaire, pour choisir
    localement le meilleur candidat. Approche simple, suffisante pour la
    construction gloutonne (la métaheuristique affinera).
    """
    ctx.add_assignment(staff_id, shift_id)
    result = scoring.total_score(ctx, aux, weights)
    ctx.remove_assignment(staff_id, shift_id)
    return result['total']


# ──────────────────────────────── Algorithme principal ───────────────────

def generate_daily_planning(target_date, service_id=None):
    """
    Génère le planning pour UNE journée (cahier Phase 3 : période = jour).

    Args:
        target_date (datetime.date) : jour à planifier.
        service_id (int|None) : si fourni, limite la génération à un service.

    Returns:
        dict : {
            'assignments': [{'shift': id, 'staff': id, 'legal': True}, ...],
            'uncovered':   [{'shift': id, 'missing': n, 'reason': str}, ...],
            'score':       { total, details, weights },
            'summary':     { shifts_total, covered, uncovered, staff_used },
        }
    """
    from api.models import Shift

    window_start = target_date
    window_end = target_date

    # 1. Snapshot in-memory
    ctx = FeasibilityContext.from_db(window_start, window_end)
    aux = _load_aux_data(window_start, window_end)
    weights = scoring.load_weights()

    # 2. Liste des shifts à planifier ce jour (filtré service si demandé)
    qs = Shift.objects.filter(start_datetime__date=target_date)
    if service_id is not None:
        qs = qs.filter(care_unit__service_id=service_id)
    shift_ids = list(qs.values_list('id', flat=True))

    all_staff_ids = aux['all_staff_ids']

    # 3. MRV : trier par (slots_restants, candidats_légaux asc)
    def candidate_count(shift_id):
        already = ctx.current_staff_count(shift_id)
        slots_left = max(0, ctx.shifts[shift_id]['max_staff'] - already)
        if slots_left <= 0:
            return (0, 10**9)
        cnt = 0
        for sid in all_staff_ids:
            ok, _ = ctx.is_assignment_legal(sid, shift_id)
            if ok:
                cnt += 1
        return (slots_left, cnt)

    shift_ids.sort(key=lambda sid: (
        0 if ctx.shifts[sid]['is_night'] else 1,   # nuits d'abord (plus contraintes)
        candidate_count(sid)[1],                    # moins de candidats = plus urgent
    ))

    # 4. Boucle gloutonne
    new_assignments = []
    uncovered = []

    for shift_id in shift_ids:
        s = ctx.shifts[shift_id]
        already = ctx.current_staff_count(shift_id)
        target_staff = max(s['min_staff'], 1)  # au moins min_staff

        while ctx.current_staff_count(shift_id) < target_staff:
            best_staff = None
            best_key = None
            service_id_shift = s['service_id']
            load_counts = _shifts_per_staff_in_service(ctx, service_id_shift)

            for candidate in all_staff_ids:
                # Déjà affecté sur ce shift ?
                if any(sid == shift_id for (_, _, sid, _) in ctx.assignments_by_staff[candidate]):
                    continue
                ok, _ = ctx.is_assignment_legal(candidate, shift_id)
                if not ok:
                    continue

                # 1) least-loaded dans ce service (répond à M3)
                load = load_counts.get(candidate, 0)
                # 2) minimise le score total soft si on l'affecte
                delta = _local_delta_score(ctx, aux, weights, candidate, shift_id)
                key = (load, delta)

                if best_key is None or key < best_key:
                    best_key = key
                    best_staff = candidate

            if best_staff is None:
                uncovered.append({
                    'shift': shift_id,
                    'missing': target_staff - ctx.current_staff_count(shift_id),
                    'reason': 'Aucun soignant légal disponible (dures non satisfaites).',
                })
                break

            ctx.add_assignment(best_staff, shift_id)
            new_assignments.append({
                'shift': shift_id,
                'staff': best_staff,
                'legal': True,
            })

    # 5. Scoring final
    score = scoring.total_score(ctx, aux, weights)

    return {
        'assignments': new_assignments,
        'uncovered': uncovered,
        'score': score,
        'summary': {
            'shifts_total': len(shift_ids),
            'covered': len(shift_ids) - len({u['shift'] for u in uncovered}),
            'uncovered': len({u['shift'] for u in uncovered}),
            'staff_used': len({a['staff'] for a in new_assignments}),
        },
        '_ctx': ctx,   # utilisé par la métaheuristique si activée
        '_aux': aux,
        '_weights': weights,
    }
