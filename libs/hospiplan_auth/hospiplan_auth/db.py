"""Un schéma PostgreSQL par service.

- ``schema_options("identite")`` → à mettre dans ``DATABASES['default']['OPTIONS']``
  pour fixer le ``search_path``.
- ``connect_schema_creation("identite")`` (dans ``AppConfig.ready()``) crée le schéma
  s'il manque, avant les migrations : utile en local et pour la base de test.
  Sur la VM, le schéma existe déjà (créé par setup-postgres.sh).
"""
import logging
import re

from django.db import connections

logger = logging.getLogger(__name__)
_SAFE = re.compile(r"^[a-z_][a-z0-9_]*$")


def schema_options(schema):
    if not schema:
        return {}
    if not _SAFE.match(schema):
        raise ValueError(f"Nom de schéma invalide : {schema!r}")
    return {"options": f"-c search_path={schema}"}


def ensure_schema(schema, using="default"):
    if not schema:
        return
    conn = connections[using]
    if conn.vendor != "postgresql":
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", [schema])
        if cur.fetchone() is None:
            logger.info("Création du schéma %s", schema)
            cur.execute(f'CREATE SCHEMA "{schema}"')


def connect_schema_creation(schema):
    from django.db.models.signals import pre_migrate

    def _handler(sender, using="default", **kwargs):
        ensure_schema(schema, using)

    pre_migrate.connect(_handler, weak=False, dispatch_uid=f"hospiplan_ensure_schema_{schema}")
