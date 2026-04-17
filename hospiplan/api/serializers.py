from rest_framework import serializers
from django.utils import timezone
from .models import (
    Staff, Shift, ShiftAssignment, Absence, AbsenceType,
    CareUnit, ShiftType, Certification, StaffCertification,
    Preference, Service, Contract, ContractType, Role, Specialty,
)

class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Staff
        fields = '__all__'

class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Shift
        fields = '__all__'

class ShiftAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ShiftAssignment
        fields = '__all__'

class AbsenceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Absence
        fields = '__all__'

class CareUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CareUnit
        fields = '__all__'

class ShiftTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ShiftType
        fields = '__all__'

class CertificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Certification
        fields = '__all__'

class AbsenceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AbsenceType
        fields = '__all__'

class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Preference
        fields = '__all__'

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Service
        fields = '__all__'

# ─────────────────────────────────────────────────────────────────────────────
# Serializers enrichis pour la fiche soignant
# ─────────────────────────────────────────────────────────────────────────────

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Role
        fields = ['id', 'name']

class SpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Specialty
        fields = ['id', 'name']

class ContractTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ContractType
        fields = ['id', 'name', 'max_hours_per_week', 'night_shift_allowed',
                  'max_consecutive_nights', 'leave_days_per_year']

class ContractSerializer(serializers.ModelSerializer):
    contract_type = ContractTypeSerializer(read_only=True)

    class Meta:
        model  = Contract
        fields = ['id', 'contract_type', 'start_date', 'end_date', 'workload_percent']

class StaffCertificationSerializer(serializers.ModelSerializer):
    certification_name = serializers.CharField(source='certification.name', read_only=True)
    is_valid = serializers.SerializerMethodField()

    class Meta:
        model  = StaffCertification
        fields = ['id', 'certification', 'certification_name',
                  'obtained_date', 'expiration_date', 'is_valid']

    def get_is_valid(self, obj):
        today = timezone.now().date()
        if obj.expiration_date and obj.expiration_date < today:
            return False
        return True

class AbsenceDetailSerializer(serializers.ModelSerializer):
    absence_type_name = serializers.CharField(source='absence_type.name', read_only=True)
    is_active         = serializers.SerializerMethodField()

    class Meta:
        model  = Absence
        fields = ['id', 'absence_type', 'absence_type_name',
                  'start_date', 'expected_end_date', 'actual_end_date',
                  'is_planned', 'is_active']

    def get_is_active(self, obj):
        today = timezone.now().date()
        return obj.start_date <= today <= obj.expected_end_date

class PreferenceDetailSerializer(serializers.ModelSerializer):
    shift_type_name = serializers.SerializerMethodField()
    service_name    = serializers.SerializerMethodField()

    class Meta:
        model  = Preference
        fields = ['id', 'kind', 'importance', 'description',
                  'is_hard_constraint', 'start_date', 'end_date',
                  'target_shift_type', 'shift_type_name',
                  'target_service', 'service_name',
                  'target_day_of_week']

    def get_shift_type_name(self, obj):
        return obj.target_shift_type.name if obj.target_shift_type else None

    def get_service_name(self, obj):
        return obj.target_service.name if obj.target_service else None


class StaffProfileSerializer(serializers.ModelSerializer):
    """Sérialiseur complet pour la fiche soignant (lecture seule)."""
    roles         = RoleSerializer(many=True, read_only=True)
    specialties   = SpecialtySerializer(many=True, read_only=True)
    contracts     = ContractSerializer(many=True, read_only=True)
    certifications = StaffCertificationSerializer(many=True, read_only=True)
    absences      = AbsenceDetailSerializer(many=True, read_only=True)
    preferences   = PreferenceDetailSerializer(many=True, read_only=True)
    is_absent_today = serializers.SerializerMethodField()
    active_contract = serializers.SerializerMethodField()

    class Meta:
        model  = Staff
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'is_active',
                  'roles', 'specialties', 'contracts', 'active_contract',
                  'certifications', 'absences', 'preferences', 'is_absent_today']

    def get_is_absent_today(self, obj):
        today = timezone.now().date()
        return obj.absences.filter(
            start_date__lte=today,
            expected_end_date__gte=today
        ).exists()

    def get_active_contract(self, obj):
        today = timezone.now().date()
        from django.db.models import Q
        contract = obj.contracts.filter(
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).select_related('contract_type').first()
        if contract:
            return ContractSerializer(contract).data
        return None
