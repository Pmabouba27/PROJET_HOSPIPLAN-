from django.contrib import admin
from .models import (
    Staff, Role, Specialty,
    ContractType, Contract,
    Certification, StaffCertification,
    Service, CareUnit, ServiceStatus, StaffServiceAssignment,
    ShiftType, Shift, ShiftAssignment,
    AbsenceType, Absence,
    Preference,
    PatientLoad,
    StaffLoan,
    Rule,
    SoftConstraintWeight,
)

admin.site.register(Staff)
admin.site.register(Role)
admin.site.register(Specialty)
admin.site.register(ContractType)
admin.site.register(Contract)
admin.site.register(Certification)
admin.site.register(StaffCertification)
admin.site.register(Service)
admin.site.register(CareUnit)
admin.site.register(ServiceStatus)
admin.site.register(StaffServiceAssignment)
admin.site.register(ShiftType)
admin.site.register(Shift)
admin.site.register(ShiftAssignment)
admin.site.register(AbsenceType)
admin.site.register(Absence)
admin.site.register(Preference)
admin.site.register(PatientLoad)
admin.site.register(StaffLoan)
admin.site.register(Rule)
admin.site.register(SoftConstraintWeight)