"""Données de démonstration : un établissement et un compte par rôle.
Le mot de passe vient de l'environnement (SEED_PASSWORD), jamais du code."""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comptes.models import Etablissement, Utilisateur

Role = Utilisateur.Role


class Command(BaseCommand):
    help = "Crée l'établissement de démo et les comptes superadmin / admin / cadre / soignant."

    def add_arguments(self, parser):
        parser.add_argument("--soignant-staff-id", type=int, default=1,
                            help="Identifiant de la fiche soignant (service personnel) du compte SOIGNANT.")
        parser.add_argument("--domaine", default="hospiplan.demo")

    @transaction.atomic
    def handle(self, *args, soignant_staff_id, domaine, **opts):
        password = os.environ.get("SEED_PASSWORD")
        if not password or len(password) < 10:
            raise CommandError("Définir SEED_PASSWORD (10 caractères minimum) dans l'environnement.")

        etab, _ = Etablissement.objects.update_or_create(
            siret="00000000000001",
            defaults={"nom": "CHU Démo", "ville": "Lyon", "plan": Etablissement.Plan.STANDARD,
                      "statut_abonnement": Etablissement.Statut.ACTIF, "max_soignants": 300},
        )
        comptes = [
            ("superadmin", Role.SUPERADMIN, None, None),
            ("admin", Role.ADMIN, etab, None),
            ("cadre", Role.CADRE, etab, None),
            ("soignant", Role.SOIGNANT, etab, soignant_staff_id),
        ]
        for prefix, role, etablissement, staff_id in comptes:
            email = f"{prefix}@{domaine}"
            user, created = Utilisateur.objects.update_or_create(
                email=email,
                defaults={"role": role, "etablissement": etablissement, "staff_id": staff_id,
                          "first_name": prefix.capitalize(), "last_name": "Démo", "is_active": True,
                          "is_staff": role == Role.SUPERADMIN, "is_superuser": role == Role.SUPERADMIN},
            )
            user.set_password(password)
            user.full_clean(exclude=["password"])
            user.save()
            self.stdout.write(f"{'créé' if created else 'mis à jour'} : {email} ({role})")
        self.stdout.write(self.style.SUCCESS(f"Établissement « {etab.nom} » id={etab.pk}"))
