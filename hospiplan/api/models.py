from django.db import models


# =========================
# F-01 Personnel & Profils
# =========================

class Staff(models.Model):
    first_name = models.CharField(max_length=100)
    last_name  = models.CharField(max_length=100)
    email      = models.EmailField(unique=True)
    phone      = models.CharField(max_length=20, blank=True, null=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Role(models.Model):
    name = models.CharField(max_length=100)  # médecin, infirmier...

    class Meta:
        db_table = "role"

    def __str__(self):
        return self.name


class StaffRole(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    role  = models.ForeignKey(Role,  on_delete=models.CASCADE)

    class Meta:
        db_table = "staff_role"
        unique_together = ("staff", "role")

    def __str__(self):
        return f"{self.staff} — {self.role}"


class Specialty(models.Model):
    name      = models.CharField(max_length=100)
    parent    = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children"
    )  # hiérarchie récursive

    class Meta:
        db_table = "specialty"

    def __str__(self):
        return self.name


class StaffSpecialty(models.Model):
    staff     = models.ForeignKey(Staff,     on_delete=models.CASCADE)
    specialty = models.ForeignKey(Specialty, on_delete=models.CASCADE)

    class Meta:
        db_table = "staff_specialty"
        unique_together = ("staff", "specialty")

    def __str__(self):
        return f"{self.staff} — {self.specialty}"


# =========================
# F-02 Contrats
# =========================

class ContractType(models.Model):
    name                 = models.CharField(max_length=100)  # CDI, CDD, intérim...
    max_hours_per_week   = models.IntegerField()
    leave_days_per_year  = models.IntegerField()
    night_shift_allowed  = models.BooleanField(default=True)

    class Meta:
        db_table = "contract_type"

    def __str__(self):
        return self.name


class Contract(models.Model):
    staff             = models.ForeignKey(Staff,        on_delete=models.CASCADE)
    contract_type     = models.ForeignKey(ContractType, on_delete=models.CASCADE)
    start_date        = models.DateField()
    end_date          = models.DateField(null=True, blank=True)  # NULL = en cours
    workload_percent  = models.IntegerField(default=100)  # 100=plein temps, 50=mi-temps

    class Meta:
        db_table = "contract"

    def __str__(self):
        return f"{self.staff} — {self.contract_type} ({self.start_date})"


# =========================
# F-03 Certifications
# =========================

class Certification(models.Model):
    name = models.CharField(max_length=150)

    class Meta:
        db_table = "certification"

    def __str__(self):
        return self.name


class CertificationDependency(models.Model):
    parent_cert   = models.ForeignKey(
        Certification,
        on_delete=models.CASCADE,
        related_name="dependencies"
    )
    required_cert = models.ForeignKey(
        Certification,
        on_delete=models.CASCADE,
        related_name="required_by"
    )

    class Meta:
        db_table = "certification_dependency"
        unique_together = ("parent_cert", "required_cert")

    def __str__(self):
        return f"{self.parent_cert} requiert {self.required_cert}"


class StaffCertification(models.Model):
    staff           = models.ForeignKey(Staff,         on_delete=models.CASCADE)
    certification   = models.ForeignKey(Certification, on_delete=models.CASCADE)
    obtained_date   = models.DateField()
    expiration_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "staff_certification"

    def __str__(self):
        return f"{self.staff} — {self.certification}"

    def is_valid(self, at_date=None):
        """Retourne True si la certification est valide à une date donnée"""
        from django.utils import timezone
        check_date = at_date or timezone.now().date()
        if self.expiration_date is None:
            return True
        return self.expiration_date >= check_date


# =========================
# F-04 Services & Unités
# =========================

class Service(models.Model):
    name             = models.CharField(max_length=100)
    manager          = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_services"
    )
    bed_capacity      = models.IntegerField()
    criticality_level = models.IntegerField()

    class Meta:
        db_table = "service"

    def __str__(self):
        return self.name


class CareUnit(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    name    = models.CharField(max_length=100)

    class Meta:
        db_table = "care_unit"

    def __str__(self):
        return f"{self.name} ({self.service})"


class ServiceStatus(models.Model):
    STATUS_CHOICES = [
        ("ouvert",        "Ouvert"),
        ("ferme",         "Fermé"),
        ("sous-effectif", "Sous-effectif"),
    ]
    service    = models.ForeignKey(Service, on_delete=models.CASCADE)
    status     = models.CharField(max_length=50, choices=STATUS_CHOICES)
    start_date = models.DateField()
    end_date   = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "service_status"

    def __str__(self):
        return f"{self.service} — {self.status}"


class StaffServiceAssignment(models.Model):
    staff      = models.ForeignKey(Staff,   on_delete=models.CASCADE)
    service    = models.ForeignKey(Service, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date   = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "staff_service_assignment"

    def __str__(self):
        return f"{self.staff} → {self.service}"


# =========================
# F-05 Gardes & Créneaux
# =========================

class ShiftType(models.Model):
    name                = models.CharField(max_length=100)  # jour, nuit, week-end...
    duration_hours      = models.IntegerField()
    requires_rest_after = models.BooleanField(default=False)

    class Meta:
        db_table = "shift_type"

    def __str__(self):
        return self.name


class Shift(models.Model):
    care_unit      = models.ForeignKey(CareUnit,  on_delete=models.CASCADE)
    shift_type     = models.ForeignKey(ShiftType, on_delete=models.CASCADE)
    start_datetime = models.DateTimeField()
    end_datetime   = models.DateTimeField()
    min_staff      = models.IntegerField(default=1)
    max_staff      = models.IntegerField()

    class Meta:
        db_table = "shift"

    def __str__(self):
        return f"{self.shift_type} — {self.start_datetime}"


class ShiftRequiredCertification(models.Model):
    shift         = models.ForeignKey(Shift,         on_delete=models.CASCADE)
    certification = models.ForeignKey(Certification, on_delete=models.CASCADE)

    class Meta:
        db_table = "shift_required_certification"
        unique_together = ("shift", "certification")

    def __str__(self):
        return f"{self.shift} exige {self.certification}"


class ShiftAssignment(models.Model):
    shift       = models.ForeignKey(Shift, on_delete=models.CASCADE)
    staff       = models.ForeignKey(Staff, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shift_assignment"

    def __str__(self):
        return f"{self.staff} → {self.shift}"


# =========================
# F-06 Absences
# =========================

class AbsenceType(models.Model):
    name          = models.CharField(max_length=100)
    impacts_quota = models.BooleanField(default=False)

    class Meta:
        db_table = "absence_type"

    def __str__(self):
        return self.name


class Absence(models.Model):
    staff             = models.ForeignKey(Staff,       on_delete=models.CASCADE)
    absence_type      = models.ForeignKey(AbsenceType, on_delete=models.CASCADE)
    start_date        = models.DateField()
    expected_end_date = models.DateField()
    actual_end_date   = models.DateField(null=True, blank=True)
    is_planned        = models.BooleanField(default=True)

    class Meta:
        db_table = "absence"

    def __str__(self):
        return f"{self.staff} absent du {self.start_date} au {self.expected_end_date}"


# =========================
# F-07 Préférences & Contraintes
# =========================

class Preference(models.Model):
    TYPE_CHOICES = [
        ("preference", "Préférence"),
        ("contrainte", "Contrainte"),
    ]
    staff               = models.ForeignKey(Staff, on_delete=models.CASCADE)
    type                = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description         = models.CharField(max_length=255)
    is_hard_constraint  = models.BooleanField(default=False)
    start_date          = models.DateField()
    end_date            = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "preference"

    def __str__(self):
        return f"{self.staff} — {self.type}"


# =========================
# F-08 Charge patient
# =========================

class PatientLoad(models.Model):
    care_unit      = models.ForeignKey(CareUnit, on_delete=models.CASCADE)
    date           = models.DateField()
    patient_count  = models.IntegerField()
    occupancy_rate = models.FloatField()

    class Meta:
        db_table = "patient_load"
        unique_together = ("care_unit", "date")

    def __str__(self):
        return f"{self.care_unit} — {self.date} ({self.occupancy_rate}%)"


# =========================
# F-09 Prêts inter-services
# =========================

class StaffLoan(models.Model):
    staff          = models.ForeignKey(Staff,   on_delete=models.CASCADE)
    from_service   = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="loans_out")
    to_service     = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="loans_in")
    start_date     = models.DateField()
    end_date       = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "staff_loan"

    def __str__(self):
        return f"{self.staff} prêté de {self.from_service} à {self.to_service}"


# =========================
# F-10 Règles métier configurables
# =========================

class Rule(models.Model):
    name        = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    rule_type   = models.CharField(max_length=50)   # max_hours, rest_time...
    value       = models.DecimalField(max_digits=10, decimal_places=2)
    unit        = models.CharField(max_length=20)   # hours, days...
    valid_from  = models.DateField()
    valid_to    = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "rule"

    def __str__(self):
        return f"{self.name} = {self.value} {self.unit}"