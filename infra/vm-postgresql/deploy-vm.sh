#!/usr/bin/env bash
# =============================================================================
# HospiPlan — VM PostgreSQL (IaaS) sur Azure
# Crée : groupe de ressources, VNet, NSG restreint, IP publique statique, VM
# Ubuntu 24.04 avec PostgreSQL 16 (cloud-init), arrêt automatique le soir.
#
# Prérequis : az login ; une clé SSH (~/.ssh/id_ed25519.pub par défaut).
# Usage     : ./deploy-vm.sh            (variables modifiables ci-dessous ou en env)
# Aucun mot de passe n'est créé ici : ils sont générés SUR la VM par
# setup-postgres.sh (voir README.md).
# =============================================================================
set -euo pipefail

PREFIX="${PREFIX:-hospiplan}"                 # préfixe unique sur le compte partagé
SUFFIX="${SUFFIX:-$(whoami | tr -cd 'a-z0-9' | cut -c1-6)}"
LOCATION="${LOCATION:-francecentral}"
RG="${RG:-rg-${PREFIX}-${SUFFIX}}"
VM_NAME="${VM_NAME:-vm-${PREFIX}-pg}"
VM_SIZE="${VM_SIZE:-Standard_B1s}"             # 1 vCPU / 1 Gio — suffisant pour la démo
ADMIN_USER="${ADMIN_USER:-hospiadmin}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"
SHUTDOWN_TIME="${SHUTDOWN_TIME:-1900}"         # UTC — arrêt automatique (FinOps)
# IP autorisées en SSH et en PostgreSQL (votre IP publique, détectée automatiquement)
ADMIN_IP="${ADMIN_IP:-$(curl -s https://api.ipify.org)}"
# IP sortantes des App Service (à renseigner après leur création, séparées par des espaces)
APP_SERVICE_IPS="${APP_SERVICE_IPS:-}"

TAGS="projet=hospiplan environnement=demo proprietaire=${SUFFIX}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[[ -f "$SSH_KEY" ]] || { echo "Clé SSH introuvable : $SSH_KEY (ssh-keygen -t ed25519)"; exit 1; }
[[ -n "$ADMIN_IP" ]] || { echo "Impossible de détecter ADMIN_IP"; exit 1; }

echo ">> Groupe de ressources $RG ($LOCATION)"
az group create -n "$RG" -l "$LOCATION" --tags $TAGS -o none

echo ">> NSG : SSH et PostgreSQL uniquement depuis $ADMIN_IP ${APP_SERVICE_IPS}"
az network nsg create -g "$RG" -n "nsg-${VM_NAME}" --tags $TAGS -o none
az network nsg rule create -g "$RG" --nsg-name "nsg-${VM_NAME}" -n Allow-SSH-Admin \
  --priority 100 --access Allow --protocol Tcp --direction Inbound \
  --source-address-prefixes "$ADMIN_IP" --destination-port-ranges 22 -o none
# shellcheck disable=SC2086
az network nsg rule create -g "$RG" --nsg-name "nsg-${VM_NAME}" -n Allow-PostgreSQL \
  --priority 110 --access Allow --protocol Tcp --direction Inbound \
  --source-address-prefixes "$ADMIN_IP" $APP_SERVICE_IPS --destination-port-ranges 5432 -o none
# Tout le reste est refusé par la règle par défaut DenyAllInBound (65500).

echo ">> Réseau virtuel"
az network vnet create -g "$RG" -n "vnet-${PREFIX}" --address-prefix 10.20.0.0/16 \
  --subnet-name snet-data --subnet-prefix 10.20.1.0/24 --tags $TAGS -o none
az network public-ip create -g "$RG" -n "pip-${VM_NAME}" --sku Standard \
  --allocation-method Static --tags $TAGS -o none

echo ">> VM $VM_NAME ($VM_SIZE, Ubuntu 24.04, SSH par clé uniquement)"
az vm create -g "$RG" -n "$VM_NAME" \
  --image Ubuntu2404 --size "$VM_SIZE" \
  --admin-username "$ADMIN_USER" --ssh-key-values "$SSH_KEY" \
  --authentication-type ssh \
  --vnet-name "vnet-${PREFIX}" --subnet snet-data \
  --nsg "nsg-${VM_NAME}" --public-ip-address "pip-${VM_NAME}" \
  --os-disk-size-gb 30 --storage-sku StandardSSD_LRS \
  --custom-data "$SCRIPT_DIR/cloud-init.yaml" \
  --tags $TAGS -o none

echo ">> Arrêt automatique à ${SHUTDOWN_TIME} UTC"
az vm auto-shutdown -g "$RG" -n "$VM_NAME" --time "$SHUTDOWN_TIME" -o none

IP=$(az network public-ip show -g "$RG" -n "pip-${VM_NAME}" --query ipAddress -o tsv)
cat <<EOF

VM créée. IP publique : $IP
Étape suivante (initialise les bases et génère les mots de passe sur la VM) :

  ssh ${ADMIN_USER}@${IP} 'cloud-init status --wait'
  ssh ${ADMIN_USER}@${IP} 'sudo bash -s' < "$SCRIPT_DIR/setup-postgres.sh"

Puis ajouter les IP sortantes des App Service :
  APP_SERVICE_IPS="x.x.x.x y.y.y.y" RG=$RG ./update-nsg.sh
EOF
