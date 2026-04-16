"""
Fonction objectif - Phase 3.

On somme 7 pénalités molles (M1..M7) pondérées par des poids configurables
via le modèle `SoftConstraintWeight` (ou leurs valeurs par défaut si non
présents en BD).

Rappel : les contraintes dures n'apparaissent PAS ici - elles sont garanties
par `feasibility.FeasibilityContext.is_assignment_legal()` en amont. Ce
module ne voit jamais qu'un planning déjà admissible ; il sert juste à le
classer par qualité RH.
"""

from collections import defaultdict
from datetime import timedelta
from statistics import pstdev

# Poids par défaut (ajustables via SoftConstraintWeight en base)
DEFAULT_WEIGHTS = {
    'M1': 5.0,
    'M2': 1.0,
    'M3': 3.0,
    'M4': 2.0,
    'M5': 4.0,
    'M6': 2.5,
    'M7': 3.0,
    'ADAPTATION_DAYS': 14.0,
}


def load_weights():
    """Charge les poids depuis la BD (avec fallback sur DEFAULT_WEIGHTS)."""
    from api.models import SoftConstraintWeight
    w = dict(DEFAULT_WEIGHTS)
    for row in SoftConstraintWeight.objects.all():
        w[row.code] = row.weight
    return w


# ───────────────────────────────────── Helpers ───────────────────────────

def _assignments_flat(ctx):
    """
    Retourne une liste [(staff_id, shift_id, start_dt, end_dt, is_night, service_id)]
    à partir du FeasibilityContext — seulement pour les shifts de la fenêtre
    courante (ceux présents dans ctx.shifts).
    """
    out = []
    for staff_id, lst in ctx.assignments_by_staff.items():
        for (start, end, shift_id, is_night) in lst:
            if shift_id in ctx.shifts:
                s = ctx.shifts[shift_id]
                out.append((staff_id, shift_id, start, end, is_night, s['service_id']))
    return out


# ───────────────────────────── Pénalités individuelles ───────────────────

def penalty_M1_consecutive_nights(ctx):
    """
    M1 - éviter > N nuits consécutives (N = ContractType.max_consecutive_nights).
    Pénalité quadratique sur le dépassement pour dissuader les gros abus.
    """
    pen = 0.0
    for staff_id, lst in ctx.assignments_by_staff.items():
        nights = sorted(
            [(a_start.date(), a_start, a_end) for (a_start, a_end, _, is_night) in lst if is_night]
        )
        if not nights:
            continue

        # plus longue série consécutive
        run = 1
        max_run = 1
        for i in range(1, len(nights)):
            if nights[i][0] - nights[i - 1][0] == timedelta(days=1):
                run += 1
                max_run = max(max_run, run)
            else:
                run = 1

        # N dépend du contrat actif le jour de la 1ère nuit
        first_date = nights[0][0]
        contract = ctx.contract_at(staff_id, first_date)
        n_max = contract[4] if contract else 3
        over = max(0, max_run - n_max)
        pen += over * over
    return pen


def penalty_M2_preferences(ctx, preferences_by_staff):
    """
    M2 - respect des préférences F-07 pondérées par leur importance.
    `preferences_by_staff` est préchargé par le générateur depuis la BD :
        staff_id -> list[dict(kind, importance, target_shift_type_id,
                              target_service_id, target_day_of_week,
                              start_date, end_date)]
    """
    pen = 0.0
    flat = _assignments_flat(ctx)
    for (staff_id, shift_id, start, end, is_night, service_id) in flat:
        d = start.date()
        dow = start.weekday()
        s = ctx.shifts[shift_id]
        stype_id = s['shift_type_id']
        for p in preferences_by_staff.get(staff_id, []):
            if p['start_date'] and d < p['start_date']:
                continue
            if p['end_date'] and d > p['end_date']:
                continue
            kind = p['kind']
            imp = p['importance']
            violated = False
            if kind == 'wants_shift_type' and p['target_shift_type_id'] != stype_id:
                violated = True
            elif kind == 'avoids_shift_type' and p['target_shift_type_id'] == stype_id:
                violated = True
            elif kind == 'wants_day' and p['target_day_of_week'] != dow:
                violated = True
            elif kind == 'avoids_day' and p['target_day_of_week'] == dow:
                violated = True
            elif kind == 'wants_service' and p['target_service_id'] != service_id:
                violated = True
            elif kind == 'avoids_service' and p['target_service_id'] == service_id:
                violated = True
            if violated:
                pen += imp
    return pen


def penalty_M3_workload_std(ctx, role_by_staff):
    """
    M3 - équilibrer la charge entre soignants de même grade (role) dans un service.
    Pénalité = somme des écarts-types du nombre de gardes par (role, service).
    """
    # (role_id, service_id) -> staff_id -> count
    groups = defaultdict(lambda: defaultdict(int))
    flat = _assignments_flat(ctx)
    for (staff_id, shift_id, _, _, _, service_id) in flat:
        for role_id in role_by_staff.get(staff_id, []):
            groups[(role_id, service_id)][staff_id] += 1

    pen = 0.0
    for counts in groups.values():
        if len(counts) >= 2:
            pen += pstdev(counts.values())
    return pen


def penalty_M4_service_switches(ctx, window_start, window_end):
    """
    M4 - minimiser les changements de service sur une même semaine.
    Pénalité = Σ_staff (nb_services_distincts_semaine - 1), positive uniquement.
    Calcule par semaine iso puis somme.
    """
    pen = 0.0
    # staff -> week_start -> set(service_id)
    buckets = defaultdict(lambda: defaultdict(set))
    flat = _assignments_flat(ctx)
    for (staff_id, shift_id, start, end, _, service_id) in flat:
        d = start.date()
        if not (window_start <= d <= window_end):
            continue
        week = d - timedelta(days=d.weekday())
        buckets[staff_id][week].add(service_id)
    for weeks in buckets.values():
        for services in weeks.values():
            if len(services) > 1:
                pen += (len(services) - 1)
    return pen


def penalty_M5_weekend_equity(ctx, all_staff_ids, trimester_start, trimester_end):
    """
    M5 - équité des gardes de week-end sur le trimestre.
    Pénalité = écart-type du nombre de gardes de week-end par soignant, sur tout
    le trimestre courant (la fenêtre générée + historique inclus dans ctx).
    """
    counts = {sid: 0 for sid in all_staff_ids}
    for staff_id, lst in ctx.assignments_by_staff.items():
        if staff_id not in counts:
            counts[staff_id] = 0
        for (a_start, _, _, _) in lst:
            d = a_start.date()
            if trimester_start <= d <= trimester_end and d.weekday() >= 5:
                counts[staff_id] += 1
    if len(counts) >= 2:
        return pstdev(counts.values())
    return 0.0


def penalty_M6_adaptation(ctx, staff_service_history, staff_loans, adaptation_days):
    """
    M6 - éviter d'affecter à un service jamais travaillé sans adaptation.
    `staff_service_history` : staff_id -> set(service_id) (historique des StaffServiceAssignment clos).
    `staff_loans` : staff_id -> list[(from_service_id, to_service_id, start, end)]
    Pénalité = w6 si affectation sur service inconnu ET non couvert par un prêt actif.
    """
    pen = 0.0
    flat = _assignments_flat(ctx)
    for (staff_id, shift_id, start, end, _, service_id) in flat:
        known = staff_service_history.get(staff_id, set())
        if service_id in known:
            continue
        # prêt en cours couvrant ce jour et ce service ?
        covered = False
        d = start.date()
        for (_, to_svc, ls, le) in staff_loans.get(staff_id, []):
            if to_svc == service_id and ls <= d <= le:
                covered = True
                break
        if not covered:
            pen += 1.0
    return pen


def penalty_M7_care_continuity(ctx, services_requiring_continuity):
    """
    M7 - favoriser la continuité de soins : même soignant sur la même
    care_unit sur jours consécutifs (approximation patient).
    Pénalité = nombre de « ruptures » (jour J a un soignant qui n'était pas
    présent en J-1) dans les care_units des services marqués
    `requires_care_continuity`.
    """
    # (care_unit_id, date) -> set(staff_id)
    presence = defaultdict(set)
    flat = _assignments_flat(ctx)
    for (staff_id, shift_id, start, end, _, service_id) in flat:
        if service_id not in services_requiring_continuity:
            continue
        care_unit_id = ctx.shifts[shift_id]['care_unit_id']
        d = start.date()
        presence[(care_unit_id, d)].add(staff_id)

    # parcours des care_units
    by_unit = defaultdict(dict)  # care_unit_id -> date -> set
    for (cu, d), staff_set in presence.items():
        by_unit[cu][d] = staff_set

    pen = 0.0
    for cu, days in by_unit.items():
        sorted_days = sorted(days.keys())
        for i in range(1, len(sorted_days)):
            d_prev = sorted_days[i - 1]
            d_cur = sorted_days[i]
            if (d_cur - d_prev).days == 1:
                prev_staff = days[d_prev]
                cur_staff = days[d_cur]
                # ruptures = staff présents en J mais absents en J-1
                pen += len(cur_staff - prev_staff)
    return pen


# ───────────────────────────── Fonction objectif totale ──────────────────

def total_score(ctx, aux, weights=None):
    """
    Agrège M1..M7 en un score scalaire pondéré, à minimiser.

    `aux` (dict) : données auxiliaires préchargées par le générateur pour
    éviter de re-taper la BD à chaque évaluation :
        - preferences_by_staff
        - role_by_staff
        - all_staff_ids
        - staff_service_history
        - staff_loans
        - services_requiring_continuity
        - window_start, window_end
        - trimester_start, trimester_end
    """
    if weights is None:
        weights = load_weights()

    m1 = penalty_M1_consecutive_nights(ctx)
    m2 = penalty_M2_preferences(ctx, aux['preferences_by_staff'])
    m3 = penalty_M3_workload_std(ctx, aux['role_by_staff'])
    m4 = penalty_M4_service_switches(ctx, aux['window_start'], aux['window_end'])
    m5 = penalty_M5_weekend_equity(ctx, aux['all_staff_ids'],
                                   aux['trimester_start'], aux['trimester_end'])
    m6 = penalty_M6_adaptation(ctx, aux['staff_service_history'], aux['staff_loans'],
                               weights['ADAPTATION_DAYS'])
    m7 = penalty_M7_care_continuity(ctx, aux['services_requiring_continuity'])

    total = (
        weights['M1'] * m1 +
        weights['M2'] * m2 +
        weights['M3'] * m3 +
        weights['M4'] * m4 +
        weights['M5'] * m5 +
        weights['M6'] * m6 +
        weights['M7'] * m7
    )

    return {
        'total': total,
        'details': {
            'M1_consecutive_nights': m1,
            'M2_preferences': m2,
            'M3_workload_std': m3,
            'M4_service_switches': m4,
            'M5_weekend_equity': m5,
            'M6_adaptation': m6,
            'M7_care_continuity': m7,
        },
        'weights': weights,
    }
