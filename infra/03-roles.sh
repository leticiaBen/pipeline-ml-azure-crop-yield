#!/usr/bin/env bash
# =============================================================================
#  Attributions de rôles — à exécuter par la PROPRIÉTAIRE de l'abonnement
#
#  Pourquoi un script à part : le rôle Contributor ne permet pas de créer des
#  attributions de rôles (AuthorizationFailed sur
#  Microsoft.Authorization/roleAssignments/write). L'identité GitHub, qui est
#  Contributor sur le groupe, ne peut donc pas les appliquer elle-même. Ces
#  commandes restent hors du pipeline CI/CD, par conception.
#
#  --assignee-object-id évite toute lecture de l'annuaire Entra ID, souvent
#  interdite aux comptes étudiants.
# =============================================================================
set -euo pipefail

EQ=cropyield
RG=rg-projet-$EQ
ST=st${EQ}pipe
COSMOS=cosmos-$EQ
FUNC=func-$EQ
ID=id-github-$EQ

# -----------------------------------------------------------------------------
# 1. Identité GitHub Actions → Contributor sur le GROUPE uniquement  [FAIT]
#    Elle déploie, mais ne peut pas créer d'attributions de rôles.
# -----------------------------------------------------------------------------
GH_PID=$(az identity show -n "$ID" -g "$RG" --query principalId -o tsv)
az role assignment create --role Contributor \
  --assignee-object-id "$GH_PID" \
  --assignee-principal-type ServicePrincipal \
  --scope "$(az group show -n "$RG" --query id -o tsv)"

# Contrôle de moindre privilège : doit renvoyer exactement 1 ligne, portée = le groupe
az role assignment list --assignee "$GH_PID" --all \
  --query "[].{role:roleDefinitionName, portee:scope}" -o table

# -----------------------------------------------------------------------------
# 2. Identité de la Function App → Stockage et Cosmos DB
#    La Function App existe depuis 04-functions.sh, et son identité est déjà
#    assignée. Sans ces rôles, le code échoue sur chaque accès :
#    DefaultAzureCredential obtient un jeton valide, mais le plan de données
#    le refuse.
# -----------------------------------------------------------------------------
PID=$(az functionapp identity show -n "$FUNC" -g "$RG" --query principalId -o tsv)
ST_ID=$(az storage account show -n "$ST" -g "$RG" --query id -o tsv)

# « Blob Data Owner » et non « Contributor » : le dispatcher doit poser des
# MÉTADONNÉES sur le blob copié dans rejected/, ce que Contributor ne couvre
# pas pour toutes les opérations.
for r in "Storage Blob Data Owner" "Storage Queue Data Contributor"; do
  az role assignment create --role "$r" \
    --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal \
    --scope "$ST_ID"
done

# Plan de données Cosmos DB : ce n'est PAS un rôle Azure RBAC, d'où une
# commande distincte. L'identifiant est celui du rôle intégré
# « Cosmos DB Built-in Data Contributor ».
az cosmosdb sql role assignment create -a "$COSMOS" -g "$RG" --scope / \
  --principal-id "$PID" \
  --role-definition-id 00000000-0000-0000-0000-000000000002

# Contrôle : cette identité ne doit avoir que ces rôles, et rien au niveau de
# l'abonnement.
az role assignment list --assignee "$PID" --all \
  --query "[].{role:roleDefinitionName, portee:scope}" -o table
