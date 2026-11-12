from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class Etablissement(models.Model):
    """Établissement client du SaaS (tenant)."""

    class Plan(models.TextChoices):
        ESSAI = "ESSAI", "Essai (30 jours)"
        STANDARD = "STANDARD", "Standard"
        PREMIUM = "PREMIUM", "Premium"

    class Statut(models.TextChoices):
        ACTIF = "ACTIF", "Actif"
        SUSPENDU = "SUSPENDU", "Suspendu (impayé)"
        RESILIE = "RESILIE", "Résilié"

    nom = models.CharField(max_length=255)
    siret = models.CharField(
        max_length=14, unique=True,
        validators=[RegexValidator(r"^\d{14}$", "Le SIRET doit contenir 14 chiffres.")],
    )
    ville = models.CharField(max_length=120)
    plan = models.CharField(max_length=16, choices=Plan.choices, default=Plan.ESSAI)
    statut_abonnement = models.CharField(max_length=16, choices=Statut.choices, default=Statut.ACTIF)
    max_soignants = models.PositiveIntegerField(default=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "etablissement"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    @property
    def est_actif(self):
        return self.statut_abonnement == self.Statut.ACTIF


class UtilisateurManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("L'email est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Utilisateur.Role.SOIGNANT)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(role=Utilisateur.Role.SUPERADMIN, is_staff=True, is_superuser=True, etablissement=None)
        return self._create_user(email, password, **extra)


class Utilisateur(AbstractUser):
    """Compte de connexion. Le lien vers la fiche soignant est un identifiant
    (``staff_id``) du service personnel, pas une clé étrangère."""

    class Role(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", "Éditeur SaaS"
        ADMIN = "ADMIN", "Administrateur d'établissement"
        CADRE = "CADRE", "Cadre de santé"
        SOIGNANT = "SOIGNANT", "Soignant"

    username = None
    email = models.EmailField("email", unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.SOIGNANT)
    etablissement = models.ForeignKey(
        Etablissement, on_delete=models.PROTECT, null=True, blank=True, related_name="utilisateurs"
    )
    staff_id = models.PositiveIntegerField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UtilisateurManager()

    class Meta:
        db_table = "utilisateur"
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(
                fields=["etablissement", "staff_id"],
                condition=models.Q(staff_id__isnull=False),
                name="uniq_staff_par_etablissement",
            )
        ]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = (self.email or "").lower()
        if self.role == self.Role.SUPERADMIN:
            if self.etablissement_id is not None:
                raise ValidationError({"etablissement": "Un SUPERADMIN n'est rattaché à aucun établissement."})
        elif self.etablissement_id is None:
            raise ValidationError({"etablissement": "Établissement obligatoire pour ce rôle."})
        if self.role == self.Role.SOIGNANT and self.staff_id is None:
            raise ValidationError({"staff_id": "Un SOIGNANT doit être lié à une fiche soignant (staff_id)."})
