"""
Peuple la base avec un jeu de données réaliste pour la démo Phase 3.

Usage :
    python manage.py seed_phase3
    python manage.py seed_phase3 --reset    # vide d'abord les tables métier

Crée :
  - Rôles (IDE, Aide-soignant, Médecin, Cadre)
  - Spécialités (Urgences, Cardiologie, Pédiatrie, Réanimation, Gériatrie)
  - Types de contrat (CDI plein, CDI temps partiel, CDD, Interim)
  - Types de shift (jour, nuit, week-end)
  - 5 services + 5 care_units + patient_loads
  - 3 certifications (Réa, Pédiatrie, Urgences)
  - 20 soignants complets avec :
      * rôles + spécialités
      * contrats variés (avec max_consecutive_nights)
      * certifications (réa, pédiatrie, urgences)
      * staff_service_assignments (historique)
      * absences variées (7 soignants absents)
      * préférences structurées (M2) pour 15 soignants
      * 1 soignant intérimaire (sans droit nuit) pour tester RULE_CONTRACT_ELIG
      * 1 soignant avec certification expirée pour tester RULE_CERTIF_EXP
  - Shifts pour les 14 prochains jours (fenêtre élargie pour les tests)
  - Quelques affectations de départ (historique)
  - Poids par défaut des contraintes molles (SoftConstraintWeight)
"""

import random
from datetime import date, timedelta, datetime, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from api.models import (
    Staff, Role, Specialty, ContractType, Contract,
    Certification, StaffCertification,
    Service, CareUnit, StaffServiceAssignment,
    ShiftType, Shift, ShiftAssignment,
    AbsenceType, Absence, Preference, PatientLoad,
    SoftConstraintWeight,
)


PRENOMS = [
    'Amina',   'Bastien', 'Chloé',   'Diallo',  'Élise',
    'Fatou',   'Gabriel', 'Hana',    'Inès',    'Julien',
    'Khadija', 'Lucas',   'Marion',  'Nora',    'Omar',
    'Priya',   'Quentin', 'Rania',   'Sébastien','Tania',
]
NOMS = [
    'Traoré',   'Martin',   'Lefebvre', 'Dupont',    'Moreau',
    'Diop',     'Bernard',  'Nguyen',   'Richard',   'Petit',
    'Barry',    'Rousseau', 'Bouchard', 'Okonkwo',   'Garcia',
    'Sharma',   'Lemaire',  'Benali',   'Fontaine',  'Millet',
]


class Command(BaseCommand):
    help = "Peuple la BD avec 15 soignants + données Phase 3."

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help="Vide les tables métier avant de peupler.")
        parser.add_argument('--seed', type=int, default=42,
                            help="Graine aléatoire (défaut 42, pour reproductibilité).")

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(opts['seed'])

        if opts['reset']:
            self.stdout.write(self.style.WARNING('Reset des tables métier…'))
            ShiftAssignment.objects.all().delete()
            Shift.objects.all().delete()
            Preference.objects.all().delete()
            Absence.objects.all().delete()
            StaffCertification.objects.all().delete()
            StaffServiceAssignment.objects.all().delete()
            Contract.objects.all().delete()
            PatientLoad.objects.all().delete()
            CareUnit.objects.all().delete()
            Staff.objects.all().delete()
            Service.objects.all().delete()
            ShiftType.objects.all().delete()
            Certification.objects.all().delete()
            ContractType.objects.all().delete()
            Role.objects.all().delete()
            Specialty.objects.all().delete()
            AbsenceType.objects.all().delete()
            SoftConstraintWeight.objects.all().delete()

        self.stdout.write('Création des référentiels…')

        roles = {n: Role.objects.get_or_create(name=n)[0] for n in
                 ['IDE', 'Aide-soignant', 'Médecin', 'Cadre']}
        specs = {n: Specialty.objects.get_or_create(name=n)[0] for n in
                 ['Urgences', 'Cardiologie', 'Pédiatrie', 'Réanimation', 'Gériatrie']}

        ct_cdi = ContractType.objects.get_or_create(
            name='CDI plein temps',
            defaults={'max_hours_per_week': 48, 'leave_days_per_year': 25,
                      'night_shift_allowed': True, 'max_consecutive_nights': 3})[0]
        ct_tp = ContractType.objects.get_or_create(
            name='CDI temps partiel',
            defaults={'max_hours_per_week': 28, 'leave_days_per_year': 25,
                      'night_shift_allowed': True, 'max_consecutive_nights': 2})[0]
        ct_cdd = ContractType.objects.get_or_create(
            name='CDD',
            defaults={'max_hours_per_week': 35, 'leave_days_per_year': 20,
                      'night_shift_allowed': True, 'max_consecutive_nights': 2})[0]
        ct_inter = ContractType.objects.get_or_create(
            name='Intérim (pas de nuit)',
            defaults={'max_hours_per_week': 35, 'leave_days_per_year': 10,
                      'night_shift_allowed': False, 'max_consecutive_nights': 0})[0]
        contract_types = [ct_cdi, ct_tp, ct_cdd, ct_inter]

        st_day = ShiftType.objects.get_or_create(
            name='Jour',
            defaults={'duration_hours': 8, 'requires_rest_after': False, 'is_night_shift': False})[0]
        st_night = ShiftType.objects.get_or_create(
            name='Nuit',
            defaults={'duration_hours': 10, 'requires_rest_after': True, 'is_night_shift': True})[0]
        st_we = ShiftType.objects.get_or_create(
            name='Week-end',
            defaults={'duration_hours': 12, 'requires_rest_after': True, 'is_night_shift': False})[0]

        cert_rea = Certification.objects.get_or_create(name='Réanimation niveau 2')[0]
        cert_ped = Certification.objects.get_or_create(name='Pédiatrie avancée')[0]
        cert_urg = Certification.objects.get_or_create(name='Urgences vitales')[0]

        abs_types = {n: AbsenceType.objects.get_or_create(
                        name=n, defaults={'impacts_quota': True})[0]
                     for n in ['Congés payés', 'Arrêt maladie', 'Formation', 'Congé maternité']}

        # Services + care units + patient loads
        services_data = [
            ('Urgences', 30, 5, False),
            ('Cardiologie', 25, 3, True),
            ('Pédiatrie', 20, 3, True),
            ('Réanimation', 15, 5, True),
            ('Gériatrie', 35, 2, True),
        ]
        services = {}
        care_units = {}
        for name, cap, crit, continuity in services_data:
            s, _ = Service.objects.get_or_create(
                name=name,
                defaults={'bed_capacity': cap, 'criticality_level': crit,
                          'requires_care_continuity': continuity})
            services[name] = s
            cu, _ = CareUnit.objects.get_or_create(
                service=s, name=f'Unité {name}')
            care_units[name] = cu
            # patient loads sur une semaine
            for i in range(7):
                d = date.today() + timedelta(days=i)
                PatientLoad.objects.get_or_create(
                    care_unit=cu, date=d,
                    defaults={'patient_count': random.randint(5, cap),
                              'occupancy_rate': random.uniform(0.4, 0.95)})

        self.stdout.write('Création des 20 soignants…')
        staff_list = []
        for i, (first, last) in enumerate(zip(PRENOMS, NOMS)):
            phone_digits = str(i).zfill(2)
            email = f'{first.lower()}.{last.lower()}@chu-alaamal.fr'
            s, _ = Staff.objects.get_or_create(
                email=email,
                defaults={'first_name': first, 'last_name': last,
                          'phone': f'06 {phone_digits} {phone_digits} {phone_digits} {phone_digits}',
                          'is_active': True})

            # Rôles : 60 % IDE, 20 % Aide-soignant, 15 % Médecin, 5 % Cadre
            role_name = random.choices(
                ['IDE', 'Aide-soignant', 'Médecin', 'Cadre'],
                weights=[60, 20, 15, 5])[0]
            s.roles.add(roles[role_name])
            s.specialties.add(random.choice(list(specs.values())))
            staff_list.append(s)

            # Contrat — le 16e soignant (Priya Sharma) est intérimaire
            # pour permettre de tester RULE_CONTRACT_ELIG (pas de nuit)
            if i == 15:
                ct = ct_inter
            else:
                ct = random.choices(contract_types[:3], weights=[50, 30, 20])[0]

            Contract.objects.get_or_create(
                staff=s, start_date=date(2023, 1, 1),
                defaults={
                    'contract_type': ct,
                    'workload_percent': 100 if ct == ct_cdi else 70,
                    'end_date': date(2025, 12, 31) if ct in (ct_cdd, ct_inter) else None,
                })

            # Certifications
            # - 50 % ont la certif réa valide
            if random.random() < 0.5:
                StaffCertification.objects.get_or_create(
                    staff=s, certification=cert_rea,
                    defaults={'obtained_date': date(2022, 6, 1),
                              'expiration_date': date(2028, 6, 1)})
            # - 35 % ont la certif pédiatrie valide
            if random.random() < 0.35:
                StaffCertification.objects.get_or_create(
                    staff=s, certification=cert_ped,
                    defaults={'obtained_date': date(2023, 3, 1),
                              'expiration_date': date(2027, 3, 1)})
            # - 40 % ont la certif urgences valide
            if random.random() < 0.4:
                StaffCertification.objects.get_or_create(
                    staff=s, certification=cert_urg,
                    defaults={'obtained_date': date(2021, 9, 1),
                              'expiration_date': date(2026, 9, 1)})

            # Le 17e soignant (Quentin Lemaire) a une certification EXPIRÉE
            # pour tester RULE_CERTIF_EXP
            if i == 16:
                StaffCertification.objects.get_or_create(
                    staff=s, certification=cert_rea,
                    defaults={'obtained_date': date(2018, 1, 1),
                              'expiration_date': date(2020, 1, 1)})  # expirée !

            # Historique de service (pour M6 — période d'adaptation)
            svc = random.choice(list(services.values()))
            StaffServiceAssignment.objects.get_or_create(
                staff=s, service=svc,
                defaults={'start_date': date(2023, 2, 1),
                          'end_date': date(2024, 1, 1)})

        self.stdout.write('Création des absences (7 soignants)…')
        today = date.today()

        # Absences aléatoires pour 5 soignants
        for s in random.sample(staff_list[:15], 5):
            # Éviter les doublons
            if not Absence.objects.filter(staff=s).exists():
                Absence.objects.create(
                    staff=s,
                    absence_type=random.choice(list(abs_types.values())),
                    start_date=today + timedelta(days=random.randint(-2, 3)),
                    expected_end_date=today + timedelta(days=random.randint(5, 14)),
                    is_planned=random.choice([True, False]),
                )

        # Absence déterministe pour tester RULE_ABSENCE_PRIO :
        # le 18e soignant (Rania Benali) est absent toute la semaine
        s_absent = staff_list[17] if len(staff_list) > 17 else staff_list[-1]
        if not Absence.objects.filter(staff=s_absent).exists():
            Absence.objects.create(
                staff=s_absent,
                absence_type=abs_types['Arrêt maladie'],
                start_date=today - timedelta(days=1),
                expected_end_date=today + timedelta(days=10),
                is_planned=False,
            )

        # Absence longue (congé maternité) pour un autre soignant
        s_mat = staff_list[19] if len(staff_list) > 19 else staff_list[-2]
        if not Absence.objects.filter(staff=s_mat).exists():
            Absence.objects.create(
                staff=s_mat,
                absence_type=abs_types['Congé maternité'],
                start_date=today - timedelta(days=30),
                expected_end_date=today + timedelta(days=60),
                is_planned=True,
            )

        self.stdout.write('Création des préférences structurées (15 soignants)…')
        kinds = ['wants_shift_type', 'avoids_shift_type', 'wants_day',
                 'avoids_day', 'wants_service', 'avoids_service']
        for s in random.sample(staff_list, 15):
            k = random.choice(kinds)
            p = Preference(staff=s, type='user_preference',
                           kind=k, importance=random.randint(1, 5),
                           is_hard_constraint=False,
                           description=f'Préférence auto générée ({k})')
            if k in ('wants_shift_type', 'avoids_shift_type'):
                p.target_shift_type = random.choice([st_day, st_night, st_we])
            elif k in ('wants_service', 'avoids_service'):
                p.target_service = random.choice(list(services.values()))
            elif k in ('wants_day', 'avoids_day'):
                p.target_day_of_week = random.randint(0, 6)
            p.save()

        # Contrainte IMPÉRATIVE pour tester RULE_HARD_PREF :
        # le 19e soignant (Sébastien Fontaine) refuse le vendredi
        s_hard = staff_list[18] if len(staff_list) > 18 else staff_list[-3]
        Preference.objects.get_or_create(
            staff=s_hard,
            type='hard_constraint',
            defaults={
                'kind': 'avoids_day',
                'importance': 5,
                'is_hard_constraint': True,
                'target_day_of_week': 4,   # 4 = vendredi
                'description': 'Ne peut pas travailler le vendredi (contrainte de transport)',
            }
        )

        self.stdout.write('Création des shifts sur 14 jours…')
        shifts_created = 0
        for day_offset in range(14):
            d = today + timedelta(days=day_offset)
            for cu in care_units.values():
                # Shift jour
                Shift.objects.get_or_create(
                    care_unit=cu, shift_type=st_day,
                    start_datetime=timezone.make_aware(datetime.combine(d, time(8, 0))),
                    defaults={
                        'end_datetime': timezone.make_aware(datetime.combine(d, time(16, 0))),
                        'min_staff': 2, 'max_staff': 4,
                    })
                shifts_created += 1
                # Shift nuit
                next_d = d + timedelta(days=1)
                Shift.objects.get_or_create(
                    care_unit=cu, shift_type=st_night,
                    start_datetime=timezone.make_aware(datetime.combine(d, time(22, 0))),
                    defaults={
                        'end_datetime': timezone.make_aware(datetime.combine(next_d, time(6, 0))),
                        'min_staff': 1, 'max_staff': 3,
                    })
                shifts_created += 1

        self.stdout.write('Poids par défaut des contraintes molles…')
        defaults = [
            ('M1', 5.0, 'Nuits consécutives > N'),
            ('M2', 1.0, 'Préférences F-07 (importance x 1)'),
            ('M3', 3.0, 'Équilibrage charge par grade/service'),
            ('M4', 2.0, 'Changements de service dans la semaine'),
            ('M5', 4.0, 'Équité gardes de week-end sur trimestre'),
            ('M6', 2.5, 'Adaptation nouveau service'),
            ('M7', 3.0, 'Continuité de soins'),
            ('ADAPTATION_DAYS', 14.0, 'Durée de la période d\'adaptation (jours)'),
        ]
        for code, w, desc in defaults:
            SoftConstraintWeight.objects.get_or_create(
                code=code, defaults={'weight': w, 'description': desc})

        self.stdout.write(self.style.SUCCESS(
            f"\n✔ Seed terminé :"
            f"\n    Soignants      : {Staff.objects.count()}"
            f"\n    Services       : {Service.objects.count()}"
            f"\n    Shifts         : {Shift.objects.count()} ({shifts_created} nouveaux)"
            f"\n    Absences       : {Absence.objects.count()}"
            f"\n    Préférences    : {Preference.objects.count()}"
            f"\n    Poids M        : {SoftConstraintWeight.objects.count()}"
            f"\n"
            f"\n  Soignants spéciaux pour les tests :"
            f"\n    Intérimaire (pas de nuit) : Priya Sharma (index 15)"
            f"\n    Certif expirée            : Quentin Lemaire (index 16)"
            f"\n    Absent (arrêt maladie)    : Rania Benali (index 17)"
            f"\n    Contrainte impérative     : Sébastien Fontaine (vendredi, index 18)"
            f"\n    Congé maternité           : Tania Millet (index 19)"
        ))
