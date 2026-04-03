

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q

class Rule(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    rule_type = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=50, null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name

class Staff(models.Model):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    roles = models.ManyToManyField('Role', related_name='staff_members')
    specialties = models.ManyToManyField('Specialty', related_name='staff_members')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_weekly_hours(self, date):
        # Calcul approximatif des heures sur la semaine de la date donnée
        start_week = date - timedelta(days=date.weekday())
        end_week = start_week + timedelta(days=7)
        assignments = self.shift_assignments.filter(
            shift__start_datetime__gte=start_week,
            shift__end_datetime__lte=end_week
        )
        total_seconds = sum([(a.shift.end_datetime - a.shift.start_datetime).total_seconds() for a in assignments])
        return total_seconds / 3600

class Role(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Specialty(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_specialties')

    def __str__(self):
        return self.name

class ContractType(models.Model):
    name = models.CharField(max_length=255)
    max_hours_per_week = models.IntegerField()
    leave_days_per_year = models.IntegerField()
    night_shift_allowed = models.BooleanField(default=True) # Ajouté pour RULE_CONTRACT_ELIG

    def __str__(self):
        return self.name

class Contract(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='contracts')
    contract_type = models.ForeignKey(ContractType, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    workload_percent = models.IntegerField()

class Certification(models.Model):
    name = models.CharField(max_length=255)
    dependencies = models.ManyToManyField('self', symmetrical=False, related_name='required_for')

    def __str__(self):
        return self.name

class StaffCertification(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='certifications')
    certification = models.ForeignKey(Certification, on_delete=models.CASCADE)
    obtained_date = models.DateField()
    expiration_date = models.DateField(null=True, blank=True)

    def is_valid_at(self, date):
        if self.expiration_date and self.expiration_date < date:
            return False
        return True

class Service(models.Model):
    name = models.CharField(max_length=255)
    manager = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_services')
    bed_capacity = models.IntegerField()
    criticality_level = models.IntegerField()

    def __str__(self):
        return self.name

class CareUnit(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='units')
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class ServiceStatus(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='statuses')
    status = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

class StaffServiceAssignment(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='service_assignments')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

class ShiftType(models.Model):
    name = models.CharField(max_length=255)
    duration_hours = models.IntegerField()
    requires_rest_after = models.BooleanField(default=False)
    is_night_shift = models.BooleanField(default=False) # Ajouté pour RULE_MIN_REST et RULE_CONTRACT_ELIG

    def __str__(self):
        return self.name

class Shift(models.Model):
    care_unit = models.ForeignKey(CareUnit, on_delete=models.CASCADE, related_name='shifts')
    shift_type = models.ForeignKey(ShiftType, on_delete=models.PROTECT)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    min_staff = models.IntegerField()
    max_staff = models.IntegerField()
    required_certifications = models.ManyToManyField(Certification, related_name='required_shifts')

    def __str__(self):
        return f"{self.care_unit.name} - {self.shift_type.name} ({self.start_datetime})"

class ShiftAssignment(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='assignments')
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='shift_assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # 1. RULE_NO_OVERLAP: Un soignant ne peut pas avoir deux gardes sur le même créneau
        overlapping = ShiftAssignment.objects.filter(
            staff=self.staff,
            shift__start_datetime__lt=self.shift.end_datetime,
            shift__end_datetime__gt=self.shift.start_datetime
        ).exclude(pk=self.pk)
        if overlapping.exists():
            raise ValidationError("RULE_NO_OVERLAP: Ce soignant a déjà une garde sur ce créneau.")

        # 2. RULE_ABSENCE_PRIO: Interdiction d'affecter un soignant absent
        absences = Absence.objects.filter(
            staff=self.staff,
            start_date__lte=self.shift.start_datetime.date(),
            expected_end_date__gte=self.shift.start_datetime.date()
        )
        if absences.exists():
            raise ValidationError("RULE_ABSENCE_PRIO: Le soignant est déclaré absent sur cette période.")

        # 3. RULE_CERTIF_REQ & RULE_CERTIF_EXP: Vérification des certifications
        required_certs = self.shift.required_certifications.all()
        for cert in required_certs:
            staff_cert = StaffCertification.objects.filter(staff=self.staff, certification=cert).first()
            if not staff_cert:
                raise ValidationError(f"RULE_CERTIF_REQ: Le soignant n'a pas la certification requise : {cert.name}")
            if not staff_cert.is_valid_at(self.shift.start_datetime.date()):
                raise ValidationError(f"RULE_CERTIF_EXP: La certification {cert.name} du soignant est expirée.")

        # 4. RULE_MIN_REST: Repos de 11h après une garde de nuit
        # On cherche si le shift précédent était de nuit
        previous_shift = ShiftAssignment.objects.filter(
            staff=self.staff,
            shift__end_datetime__lte=self.shift.start_datetime
        ).order_by('-shift__end_datetime').first()

        if previous_shift and previous_shift.shift.shift_type.is_night_shift:
            rest_duration = self.shift.start_datetime - previous_shift.shift.end_datetime
            if rest_duration < timedelta(hours=11):
                raise ValidationError("RULE_MIN_REST: Un repos de 11h est obligatoire après une garde de nuit.")

        # 5. RULE_CONTRACT_ELIG: Interdiction des nuits selon le contrat
        if self.shift.shift_type.is_night_shift:
            current_contract = Contract.objects.filter(
                staff=self.staff,
                start_date__lte=self.shift.start_datetime.date(),
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=self.shift.start_datetime.date())).first()
            
            if current_contract and not current_contract.contract_type.night_shift_allowed:
                raise ValidationError("RULE_CONTRACT_ELIG: Le contrat de ce soignant n'autorise pas les gardes de nuit.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # 6. RULE_MIN_STAFF: Seuil de sécurité
        current_staff_count = self.shift.assignments.count()
        if current_staff_count <= self.shift.min_staff:
            raise ValidationError(f"RULE_MIN_STAFF: Impossible de retirer ce soignant. L'effectif tomberait sous le minimum de {self.shift.min_staff}.")
        super().delete(*args, **kwargs)

class AbsenceType(models.Model):
    name = models.CharField(max_length=255)
    impacts_quota = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Absence(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='absences')
    absence_type = models.ForeignKey(AbsenceType, on_delete=models.PROTECT)
    start_date = models.DateField()
    expected_end_date = models.DateField()
    actual_end_date = models.DateField(null=True, blank=True)
    is_planned = models.BooleanField(default=True)

    def __str__(self):
        return f"Absence {self.staff} ({self.start_date})"

class Preference(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='preferences')
    type = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    is_hard_constraint = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

class PatientLoad(models.Model):
    care_unit = models.ForeignKey(CareUnit, on_delete=models.CASCADE, related_name='patient_loads')
    date = models.DateField()
    patient_count = models.IntegerField()
    occupancy_rate = models.FloatField()

class StaffLoan(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='loans')
    from_service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='loans_from')
    to_service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='loans_to')
    start_date = models.DateField()
    end_date = models.DateField()

