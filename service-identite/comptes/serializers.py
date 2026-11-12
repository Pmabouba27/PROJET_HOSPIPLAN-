from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from hospiplan_auth.errors import ApiError

from .models import Etablissement, Utilisateur


class EtablissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Etablissement
        fields = ["id", "nom", "siret", "ville", "plan", "statut_abonnement", "max_soignants", "created_at"]
        read_only_fields = ["id", "created_at"]


class UtilisateurSerializer(serializers.ModelSerializer):
    """Objet ``user`` du contrat (CONTRATS §4). Le mot de passe n'est jamais renvoyé."""

    etablissement_id = serializers.PrimaryKeyRelatedField(
        source="etablissement", queryset=Etablissement.objects.all(), allow_null=True, required=False
    )
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})

    class Meta:
        model = Utilisateur
        fields = ["id", "email", "first_name", "last_name", "role", "etablissement_id",
                  "staff_id", "is_active", "password"]
        read_only_fields = ["id", "is_active"]
        # L'unicité (etablissement, staff_id) est vérifiée par full_clean() une fois
        # l'établissement imposé par le jeton ; le validateur DRF généré rendrait
        # etablissement_id obligatoire côté client.
        validators = []

    @property
    def _acteur(self):
        return self.context["request"].user

    def validate_email(self, value):
        value = value.lower()
        qs = Utilisateur.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ApiError(409, "CONFLICT", "Un compte existe déjà avec cet email.", {"email": value})
        return value

    def validate_role(self, value):
        if value == Utilisateur.Role.SUPERADMIN and self._acteur.role != Utilisateur.Role.SUPERADMIN:
            raise serializers.ValidationError("Seul un SUPERADMIN peut attribuer ce rôle.")
        return value

    def validate(self, attrs):
        acteur = self._acteur
        if acteur.role != Utilisateur.Role.SUPERADMIN:
            # Un ADMIN ne gère que son établissement : la valeur client est ignorée
            attrs.pop("etablissement", None)
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Mot de passe obligatoire à la création."})
        if attrs.get("password"):
            candidat = Utilisateur(email=attrs.get("email", getattr(self.instance, "email", "")),
                                   first_name=attrs.get("first_name", ""), last_name=attrs.get("last_name", ""))
            validate_password(attrs["password"], user=candidat)
        return attrs

    def _check_and_save(self, user, password):
        if password:
            user.set_password(password)
        try:
            user.full_clean(exclude=["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages)
        user.save()
        return user

    def create(self, validated_data):
        password = validated_data.pop("password")
        return self._check_and_save(Utilisateur(**validated_data), password)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        return self._check_and_save(instance, password)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={"input_type": "password"})


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ServiceTokenSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=64)
    client_secret = serializers.CharField(max_length=256)
