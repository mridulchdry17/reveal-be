#!/usr/bin/env bash
# Try to create the free Azure PostgreSQL server (Burstable B1ms, 32 GB) region by region,
# nearest first, and stop at the first region that works. Writes reveal-be/.env on success.
#
# Usage (after `az login`):  bash scripts/try_azure_postgres.sh
set -uo pipefail

RESOURCE_GROUP="reveal"
SUBSCRIPTION="Azure for Students"
ADMIN_USER="azureuser"
REGIONS=(koreasouth japaneast japanwest eastasia southeastasia southindia westindia australiaeast centralus eastus northeurope)

cd "$(dirname "$0")/.." || exit 1

az account set --subscription "$SUBSCRIPTION" || { echo "Run 'az login' first."; exit 1; }
MY_IP="$(curl -s https://api.ipify.org)"

read -rs -p "Choose the database password (16+ letters and numbers only): " PASSWORD; echo
if [[ ! "$PASSWORD" =~ ^[A-Za-z0-9]{16,}$ ]]; then
  echo "Use at least 16 letters and numbers, no symbols."; exit 1
fi

for region in "${REGIONS[@]}"; do
  name="reveal-db-${region}"
  echo ""
  echo "== Trying ${region} (server ${name}) ... this can take a few minutes"
  if az postgres flexible-server create \
      --resource-group "$RESOURCE_GROUP" \
      --name "$name" \
      --location "$region" \
      --tier Burstable \
      --sku-name Standard_B1ms \
      --storage-size 32 \
      --storage-auto-grow Disabled \
      --version 17 \
      --zonal-resiliency Disabled \
      --backup-retention 7 \
      --geo-redundant-backup Disabled \
      --admin-user "$ADMIN_USER" \
      --admin-password "$PASSWORD" \
      --public-access "$MY_IP" \
      --yes \
      --output none; then
    az postgres flexible-server db create \
      --resource-group "$RESOURCE_GROUP" --server-name "$name" --name reveal --output none \
      || echo "Server created, but creating the 'reveal' database failed. Tell Claude."
    host="${name}.postgres.database.azure.com"
    printf 'DATABASE_URL=postgresql+asyncpg://%s:%s@%s:5432/reveal?ssl=require\n' \
      "$ADMIN_USER" "$PASSWORD" "$host" > .env
    unset PASSWORD
    echo ""
    echo "SUCCESS in ${region}: ${host}"
    echo "Saved reveal-be/.env (password not printed)."
    exit 0
  fi
  echo "-- ${region} failed, cleaning up and moving on"
  az postgres flexible-server delete --resource-group "$RESOURCE_GROUP" --name "$name" --yes --output none 2>/dev/null
done

unset PASSWORD
echo ""
echo "No region accepted the free B1ms server right now."
exit 1
