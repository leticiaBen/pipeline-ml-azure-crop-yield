#!/usr/bin/env bash
# =============================================================================
#  Cree ou met a jour l'application Container Apps de l'API.
#  Idempotent : relancer le script met a jour l'application existante.
#
#  A executer par le proprietaire de l'abonnement. Le deploiement courant,
#  lui, passe par .github/workflows/deploy.yml (OIDC, sans secret Azure).
# =============================================================================
set -euo pipefail

EQ=cropyield
RG=rg-projet-$EQ
ENV=cae-$EQ
APP=api-$EQ
AI=appi-$EQ

ENV_ID=$(az containerapp env show -n "$ENV" -g "$RG" --query id -o tsv)

# Substitution de l'identifiant d'environnement dans un fichier temporaire :
# le YAML versionne ne contient pas l'identifiant d'abonnement.
DOSSIER_TMP=$(mktemp -d)
TMP="$DOSSIER_TMP/containerapp.yaml"
trap 'rm -rf "$DOSSIER_TMP"' EXIT
sed "s|__MANAGED_ENV_ID__|${ENV_ID}|" infra/02-api.yaml > "$TMP"

if az containerapp show -n "$APP" -g "$RG" >/dev/null 2>&1; then
  echo "Application existante : mise a jour"
  az containerapp update -n "$APP" -g "$RG" --yaml "$TMP" -o none
else
  echo "Creation de l'application"
  az containerapp create -n "$APP" -g "$RG" --yaml "$TMP" -o none
fi

# -----------------------------------------------------------------------------
# Telemetrie : la chaine de connexion Application Insights est un secret.
# Elle est stockee comme secret Container Apps et referencee par la variable
# d'environnement, jamais ecrite dans un fichier du depot.
# -----------------------------------------------------------------------------
CS=$(az monitor app-insights component show --app "$AI" -g "$RG" --query connectionString -o tsv)
az containerapp secret set -n "$APP" -g "$RG" --secrets "appinsights=${CS}" -o none
az containerapp update -n "$APP" -g "$RG" \
  --set-env-vars "APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appinsights" -o none

FQDN=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo "API disponible sur : https://${FQDN}"
