"""Génère une paire de clés RSA 2048 pour signer/vérifier les JWT (développement).
En production, générer la paire hors du dépôt et la saisir dans les Paramètres
d'application Azure (JWT_PRIVATE_KEY pour identite, JWT_PUBLIC_KEY pour tous)."""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Génère keys/jwt_private.pem et keys/jwt_public.pem (ignorés par git)."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default="keys")
        parser.add_argument("--force", action="store_true", help="Écrase les clés existantes.")

    def handle(self, *args, dir, force, **opts):
        out = Path(dir).resolve()
        priv_path, pub_path = out / "jwt_private.pem", out / "jwt_public.pem"
        if priv_path.exists() and not force:
            raise CommandError(f"{priv_path} existe déjà (utilisez --force pour la remplacer).")
        out.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()))
        pub_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                           serialization.PublicFormat.SubjectPublicKeyInfo))
        try:
            os.chmod(priv_path, 0o600)
        except OSError:
            pass
        self.stdout.write(self.style.SUCCESS("Clés générées. À mettre dans .env :"))
        self.stdout.write(f"JWT_PRIVATE_KEY_FILE={priv_path}")
        self.stdout.write(f"JWT_PUBLIC_KEY_FILE={pub_path}")
        self.stdout.write("Partager UNIQUEMENT la clé publique avec les autres services.")
