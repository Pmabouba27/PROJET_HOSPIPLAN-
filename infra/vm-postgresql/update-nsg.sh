#!/usr/bin/env bash
# Met à jour la règle PostgreSQL du NSG avec les IP sortantes des App Service.
# Usage : RG=rg-hospiplan-xxx APP_SERVICE_IPS="1.2.3.4 5.6.7.8" ./update-nsg.sh
# Les IP sortantes d'une App Service : az webapp show -g RG -n APP --query outboundIpAddresses -o tsv
set -euo pipefail
: "${RG:?RG requis}"; : "${APP_SERVICE_IPS:?APP_SERVICE_IPS requis}"
VM_NAME="${VM_NAME:-vm-hospiplan-pg}"
ADMIN_IP="${ADMIN_IP:-$(curl -s https://api.ipify.org)}"
# shellcheck disable=SC2086
az network nsg rule update -g "$RG" --nsg-name "nsg-${VM_NAME}" -n Allow-PostgreSQL \
  --source-address-prefixes "$ADMIN_IP" ${APP_SERVICE_IPS//,/ } -o none
az network nsg rule show -g "$RG" --nsg-name "nsg-${VM_NAME}" -n Allow-PostgreSQL \
  --query "sourceAddressPrefixes" -o tsv
