#!/usr/bin/env bash
# =============================================================================
# À exécuter SUR la VM (root) :  ssh user@IP 'sudo bash -s' < setup-postgres.sh
# - PostgreSQL écoute sur le réseau, connexions distantes en SSL + scram uniquement
# - Base "hospiplan", un schéma ET un utilisateur par microservice
# - Mots de passe générés ici, stockés dans /root/hospiplan-db-credentials (600)
#   et affichés UNE fois : les copier dans les Paramètres d'application Azure.
# Idempotent : peut être relancé (les mots de passe existants sont conservés).
# =============================================================================
set -euo pipefail

PG_VER=$(ls /etc/postgresql | sort -V | tail -1)
CONF=/etc/postgresql/$PG_VER/main
CRED=/root/hospiplan-db-credentials
DB=hospiplan
SERVICES="identite personnel planning"

# --- Configuration réseau / sécurité ---
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "$CONF/postgresql.conf"
sed -i "s/^#\?ssl = .*/ssl = on/" "$CONF/postgresql.conf"
sed -i "s/^#\?password_encryption.*/password_encryption = scram-sha-256/" "$CONF/postgresql.conf"
sed -i "s/^#\?log_connections.*/log_connections = on/" "$CONF/postgresql.conf"
sed -i "s/^#\?log_disconnections.*/log_disconnections = on/" "$CONF/postgresql.conf"

if ! grep -q "hospiplan-remote" "$CONF/pg_hba.conf"; then
  cat >> "$CONF/pg_hba.conf" <<'EOF'
# hospiplan-remote : accès distant uniquement chiffré, refus sinon
hostssl hospiplan  all  0.0.0.0/0  scram-sha-256
host    all        all  0.0.0.0/0  reject
EOF
fi
systemctl restart postgresql

# --- Mots de passe (générés une seule fois) ---
touch "$CRED" && chmod 600 "$CRED"
gen() { openssl rand -base64 33 | tr -d '/+=' | cut -c1-32; }
get_pwd() {
  local key=$1
  if ! grep -q "^${key}=" "$CRED"; then echo "${key}=$(gen)" >> "$CRED"; fi
  grep "^${key}=" "$CRED" | cut -d= -f2-
}

psql_su() { sudo -u postgres psql -v ON_ERROR_STOP=1 -q "$@"; }

psql_su -tc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1 \
  || psql_su -c "CREATE DATABASE $DB"
psql_su -d "$DB" -c "REVOKE ALL ON SCHEMA public FROM PUBLIC; REVOKE CONNECT ON DATABASE $DB FROM PUBLIC;"

# Utilisateur transitoire pour le monolithe actuel (schéma public), à supprimer après le découpage
for entry in "hospiplan_app:public" $(for s in $SERVICES; do echo "svc_${s}:${s}"; done); do
  role=${entry%%:*}; schema=${entry##*:}
  pwd=$(get_pwd "$role")
  psql_su -d "$DB" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$role') THEN
    CREATE ROLE $role LOGIN;
  END IF;
END \$\$;
ALTER ROLE $role WITH LOGIN PASSWORD '$pwd' NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 20;
GRANT CONNECT ON DATABASE $DB TO $role;
SQL
  if [[ "$schema" == "public" ]]; then
    psql_su -d "$DB" -c "GRANT USAGE, CREATE ON SCHEMA public TO $role;"
  else
    psql_su -d "$DB" -c "CREATE SCHEMA IF NOT EXISTS $schema AUTHORIZATION $role;"
    psql_su -d "$DB" -c "ALTER ROLE $role IN DATABASE $DB SET search_path = $schema;"
    psql_su -d "$DB" -c "REVOKE ALL ON SCHEMA $schema FROM PUBLIC;"
  fi
done

echo
echo "=== PostgreSQL $PG_VER prêt. Identifiants (aussi dans $CRED, lisible par root seulement) ==="
cat "$CRED"
echo "=== Les reporter dans App Service > Configuration (DB_USER / DB_PASSWORD, DB_SSLMODE=require) ==="
