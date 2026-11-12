"""Briques communes aux microservices HospiPlan (contrat : docs/contrats/CONTRATS.md §2-3).

Réglages Django attendus (dictionnaire ``HOSPIPLAN_AUTH``) :

    HOSPIPLAN_AUTH = {
        "PUBLIC_KEY": "<PEM RSA public>",            # obligatoire
        "ISSUER": "hospiplan-identite",
        "AUDIENCE_API": "hospiplan-api",
        "AUDIENCE_INTERNAL": "hospiplan-internal",
        "SERVICE_NAME": "service-xxx",               # pour /health et les logs
        "LEEWAY_SECONDS": 10,
    }
"""

ROLES = ("SUPERADMIN", "ADMIN", "CADRE", "SOIGNANT")
ROLE_RANK = {"SOIGNANT": 0, "CADRE": 1, "ADMIN": 2, "SUPERADMIN": 3}
