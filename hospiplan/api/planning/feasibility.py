"""
Oracle de faisabilité in-memory.

Ce module réplique exactement les contraintes dures vérifiées par
`ShiftAssignment.clean()` (Phase 2) mais sans passer par la base de données
à chaque test, ce qui est indispensable pour que l'heuristique gloutonne et
la métaheuristique puissent évaluer des dizaines de milliers d'affectations
candidates en un temps raisonnable.

Règles couvertes (strictement identiques à la Phase 2) :
    RULE_NO_OVERLAP       - pas deux gardes chevauchantes pour un même soignant
    RULE_ABSENCE_PRIO     - un soignant absent ne peut pas être affecté
    RULE_CERTIF_REQ       - toutes les certifications requises doivent être possédées
    RULE_CERTIF_EXP       - et elles doivent être valides à la date du shift
    RULE_MIN_REST         - 11h de repos obligatoires après une garde de nuit
    RULE_CONTRACT_ELIG    - contrats interdisant les nuits
    RULE_MIN_STAFF        - effectif minimum garanti (géré au niveau du générateur)

Design : toutes les données de référence (absences, certifs, contrats,
affectations existantes) sont chargées une seule fois dans un objet
`FeasibilityContext`, puis `is_assignment_legal()` teste une affectation
candidate contre ce contexte enrichi des affectations déjà placées par le
générateur en cours de construction.
"""

from datetime import timedelta
from collections import defaultdict


class FeasibilityContext:
    """
    Snapshot en mémoire de la base de données, utilisé comme oracle de
    faisabilité par le générateur glouton et la recherche tabou.
    """

    def __init__(self):
        # Affectations existantes (y compris celles placées par le générateur en cours).
        # Structure : staff_id -> list[(start_dt, end_dt, shift_id, shift_type_is_night)]
        self.assignments_by_staff = defaultdict(list)

        # Absences : staff_id -> list[(start_date, end_date)]
        self.absences_by_staff = defaultdict(list)

        # Certifications : staff_id -> dict[cert_id -> expiration_date or None]
        self.certifs_by_staff = defaultdict(dict)

        # Contrats : staff_id -> list[(start_date, end_date_or_None, night_allowed, max_hours_week, max_cons_nights)]
        self.contracts_by_staff = defaultdict(list)

        # Shifts : shift_id -> dict(start, end, care_unit_id, service_id, is_night,
        #                           min_staff, max_staff, required_certs={id,...})
        self.shifts = {}

    # ------------------------------------------------------------------ chargement

    @classmethod
    def from_db(cls, start_date, end_date):
        """
        Construit un FeasibilityContext en chargeant une seule fois depuis la BD
        toutes les informations utiles pour la fenêtre [start_date, end_date].

        On élargit les fenêtres de chargement des affectations et absences d'une
        semaine de part et d'autre, pour que les règles « repos après nuit » ou
        « chevauchement » restent correctes aux bords de la fenêtre générée.
        """
        from api.models import (
            ShiftAssignment, Absence, StaffCertification, Contract, Shift,
        )

        ctx = cls()

        margin = timedelta(days=7)
        lo = start_date - margin
        hi = end_date + margin

        # Affectations existantes
        existing = (
            ShiftAssignment.objects
            .select_related('shift', 'shift__shift_type')
            .filter(shift__start_datetime__date__gte=lo,
                    shift__start_datetime__date__lte=hi)
        )
        for a in existing:
            ctx.assignments_by_staff[a.staff_id].append((
                a.shift.start_datetime,
                a.shift.end_datetime,
                a.shift_id,
                a.shift.shift_type.is_night_shift,
            ))

        # Absences
        for abs_ in Absence.objects.filter(start_date__lte=hi, expected_end_date__gte=lo):
            ctx.absences_by_staff[abs_.staff_id].append(
                (abs_.start_date, abs_.expected_end_date)
            )

        # Certifications
        for sc in StaffCertification.objects.all():
            ctx.certifs_by_staff[sc.staff_id][sc.certification_id] = sc.expiration_date

        # Contrats
        for c in Contract.objects.select_related('contract_type').all():
            ct = c.contract_type
            ctx.contracts_by_staff[c.staff_id].append((
                c.start_date,
                c.end_date,
                ct.night_shift_allowed,
                ct.max_hours_per_week,
                ct.max_consecutive_nights,
            ))

        # Shifts dans la fenêtre
        shifts_qs = (
            Shift.objects
            .select_related('shift_type', 'care_unit', 'care_unit__service')
            .prefetch_related('required_certifications')
            .filter(start_datetime__date__gte=start_date,
                    start_datetime__date__lte=end_date)
        )
        for s in shifts_qs:
            ctx.shifts[s.id] = {
                'start': s.start_datetime,
                'end': s.end_datetime,
                'care_unit_id': s.care_unit_id,
                'service_id': s.care_unit.service_id,
                'is_night': s.shift_type.is_night_shift,
                'min_staff': s.min_staff,
                'max_staff': s.max_staff,
                'required_certs': {c.id for c in s.required_certifications.all()},
                'shift_type_id': s.shift_type_id,
            }

        return ctx

    # ------------------------------------------------------------------ mutations

    def add_assignment(self, staff_id, shift_id):
        """Enregistre une affectation dans le contexte (utilisé par le générateur)."""
        s = self.shifts[shift_id]
        self.assignments_by_staff[staff_id].append(
            (s['start'], s['end'], shift_id, s['is_night'])
        )

    def remove_assignment(self, staff_id, shift_id):
        """Retire une affectation du contexte (utilisé par le backtracking/tabou)."""
        self.assignments_by_staff[staff_id] = [
            t for t in self.assignments_by_staff[staff_id] if t[2] != shift_id
        ]

    # ------------------------------------------------------------------ oracle

    def is_assignment_legal(self, staff_id, shift_id):
        """
        Retourne (True, None) si l'affectation (staff_id -> shift_id) respecte
        toutes les contraintes dures, sinon (False, code_règle_violée).
        """
        if shift_id not in self.shifts:
            return False, 'RULE_UNKNOWN_SHIFT'

        s = self.shifts[shift_id]
        s_start, s_end = s['start'], s['end']

        # 1. RULE_NO_OVERLAP
        for (a_start, a_end, a_shift_id, _) in self.assignments_by_staff[staff_id]:
            if a_shift_id == shift_id:
                continue
            if a_start < s_end and a_end > s_start:
                return False, 'RULE_NO_OVERLAP'

        # 2. RULE_ABSENCE_PRIO
        shift_date = s_start.date()
        for (ab_start, ab_end) in self.absences_by_staff[staff_id]:
            if ab_start <= shift_date <= ab_end:
                return False, 'RULE_ABSENCE_PRIO'

        # 3. RULE_CERTIF_REQ & RULE_CERTIF_EXP
        staff_certs = self.certifs_by_staff[staff_id]
        for cert_id in s['required_certs']:
            if cert_id not in staff_certs:
                return False, 'RULE_CERTIF_REQ'
            exp = staff_certs[cert_id]
            if exp is not None and exp < shift_date:
                return False, 'RULE_CERTIF_EXP'

        # 4. RULE_MIN_REST : 11h après une garde de nuit
        previous = None
        for (a_start, a_end, _, a_night) in self.assignments_by_staff[staff_id]:
            if a_end <= s_start:
                if previous is None or a_end > previous[1]:
                    previous = (a_start, a_end, a_night)
        if previous is not None and previous[2]:
            if s_start - previous[1] < timedelta(hours=11):
                return False, 'RULE_MIN_REST'

        # 5. RULE_CONTRACT_ELIG : contrat interdisant les nuits
        if s['is_night']:
            for (c_start, c_end, night_ok, _, _) in self.contracts_by_staff[staff_id]:
                if c_start <= shift_date and (c_end is None or c_end >= shift_date):
                    if not night_ok:
                        return False, 'RULE_CONTRACT_ELIG'
                    break

        return True, None

    # ------------------------------------------------------------------ helpers

    def weekly_hours(self, staff_id, shift_date):
        """Heures déjà planifiées sur la semaine iso contenant shift_date."""
        monday = shift_date - timedelta(days=shift_date.weekday())
        sunday = monday + timedelta(days=6)
        total = 0.0
        for (a_start, a_end, _, _) in self.assignments_by_staff[staff_id]:
            d = a_start.date()
            if monday <= d <= sunday:
                total += (a_end - a_start).total_seconds() / 3600.0
        return total

    def contract_at(self, staff_id, shift_date):
        """Renvoie le contrat actif à cette date, ou None."""
        for c in self.contracts_by_staff[staff_id]:
            c_start, c_end, *_ = c
            if c_start <= shift_date and (c_end is None or c_end >= shift_date):
                return c
        return None

    def current_staff_count(self, shift_id):
        """Nombre de soignants déjà affectés sur ce shift (tous staff confondus)."""
        n = 0
        for staff_id, lst in self.assignments_by_staff.items():
            for (_, _, sid, _) in lst:
                if sid == shift_id:
                    n += 1
        return n
