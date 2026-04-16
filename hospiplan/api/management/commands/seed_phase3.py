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
  - 2 certifications (Réa, Pédiatrie)
  - 15 soignants complets avec :
      * rôles + spécialités
      * contrats (avec max_consecutive_nights)
      * certifications
      * staff_service_assignments (historique)
      * absences variées
      * préférences structurées (M2)
  - Shifts pour les 7 prochains jours, min_staff/max_staff réalistes
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
    'Amina', 'Bastien', 'Chloé', 'Diallo', 'Élise',
    'Fatou', 'Gabriel', 'Hana', 'Inès', 'Julien',
    'Khadija', 'Lucas', 'Marion', 'Nora', 'Omar',
]
NOMS = [
    'Traoré', 'Martin', 'Lefebvre', 'Dupont', 'Moreau',
    'Diop', 'Bernard', 'Nguyen', 'Richard', 'Petit',
    'Barry', 'Rousseau', 'Bouchard', 'Okonkwo', 'Garcia',
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

        self.stdout.write('Création des 15 soignants…')
        staff_list = []
        for i, (first, last) in enumerate(zip(PRENOMS, NOMS)):
            email = f'{first.lower()}.{last.lower()}@chu-stantoine.fr'
            s, created = Staff.objects.get_or_create(
                email=email,
                defaults={'first_name': first, 'last_name': last,
                          'phone': f'06 0{i} 0{i} 0{i} 0{i}',
                          'is_active': True})
            # roles + specialities
            role_name = random.choice(['IDE', 'IDE', 'IDE', 'Aide-soignant', 'Médecin'])
            s.roles.add(roles[role_name])
            s.specialties.add(random.choice(list(specs.values())))
            staff_list.append(s)

            # Contrat
            ct = random.choice(contract_types)
            Contract.objects.get_or_create(
                staff=s, start_date=date(2023, 1, 1),
                defaults={'contract_type': ct, 'workload_percent': 100 if ct == ct_cdi else 70})

            # Certifications (50 % ont la certif réa, 30 % la certif pédiatrie)
            if random.random() < 0.5:
                StaffCertification.objects.get_or_create(
                    staff=s, certification=cert_rea,
                    defaults={'obtained_date': date(2022, 6, 1),
                              'expiration_date': date(2028, 6, 1)})
            if random.random() < 0.3:
                StaffCertification.objects.get_or_create(
                    staff=s, certification=cert_ped,
                    defaults={'obtained_date': date(2023, 3, 1),
                              'expiration_date': date(2027, 3, 1)})

            # Historique de service (pour M6)
            svc = random.choice(list(services.values()))
            StaffServiceAssignment.objects.get_or_create(
                staff=s, service=svc,
                defaults={'start_date': date(2023, 2, 1),
                          'end_date': date(2024, 1, 1)})

        self.stdout.write('Création des absences…')
        today = date.today()
        for s in random.sample(staff_list, 5):
            Absence.objects.create(
                staff=s,
                absence_type=random.choice(list(abs_types.values())),
                start_date=today + timedelta(days=random.randint(-3, 4)),
                expected_end_date=today + timedelta(days=random.randint(5, 12)),
                is_planned=random.choice([True, False]),
            )

        self.stdout.write('Création des préférences structurées…')
        kinds = ['wants_shift_type', 'avoids_shift_type', 'wants_day',
                 'avoids_day', 'wants_service', 'avoids_service']
        for s in random.sample(staff_list, 12):
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

        self.stdout.write('Création des shifts sur 7 jours…')
        shifts_created = 0
        for day_offset in range(7):
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
            f"\n    Soignants : {Staff.objects.count()}"
            f"\n    Services  : {Service.objects.count()}"
            f"\n    Shifts    : {Shift.objects.count()} ({shifts_created} nouveaux)"
            f"\n    Absences  : {Absence.objects.count()}"
            f"\n    Préfs     : {Preference.objects.count()}"
            f"\n    Poids M   : {SoftConstraintWeight.objects.count()}"
        ))
