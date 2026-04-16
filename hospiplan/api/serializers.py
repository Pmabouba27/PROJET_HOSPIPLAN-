from rest_framework import serializers
from .models import (
    Staff, Shift, ShiftAssignment, Absence, AbsenceType,
    CareUnit, ShiftType, Certification,
    Preference, Service,
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