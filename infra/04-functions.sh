#!/usr/bin/env bash
# =============================================================================
#  Function App unique contenant les trois fonctions — section 4.3
#
#  Sur le plan Flex Consumption, un plan n'heberge qu'une seule application :
#  dispatcher, worker et recent vivent donc dans le meme function_app.py
#  (modele de programmation v2).
#
#  L'abonnement Event Grid est dans 05-eventgrid.sh : il ne peut etre cree
#  qu'APRES ce deploiement, Azure validant le point de terminaison.
# =============================================================================
set -euo pipefail

EQ=cropyield
RG=rg-projet-$EQ
LOC=francecentral
ST=st${EQ}pipe
FUNC=func-$EQ
AI=appi-$EQ
API_URL="https://api-$EQ.calmmoss-a33fdd9d.francecentral.azurecontainerapps.io"

# -----------------------------------------------------------------------------
# 1. Creation — Python 3.12, 512 Mo d'instance, comme l'exige l'enonce
# -----------------------------------------------------------------------------
az functionapp create -n "$FUNC" -g "$RG" \
  --storage-account "$ST" \
  --app-insights "$AI" \
  --flexconsumption-location "$LOC" \
  --runtime python --runtime-version 3.12 \
  --instance-memory 512

# -----------------------------------------------------------------------------
# 2. Identite attribuee par le systeme, et HTTPS uniquement
#    L'identite est ce qui permet au code d'atteindre le stockage et Cosmos
#    sans aucune chaine de connexion. Les roles sont dans 03-roles.sh.
#    httpsOnly n'est pas active par defaut : il faut le poser.
# -----------------------------------------------------------------------------
az functionapp identity assign -n "$FUNC" -g "$RG"
az functionapp update -n "$FUNC" -g "$RG" --set httpsOnly=true

# -----------------------------------------------------------------------------
# 3. Reglages d'application — aucun secret, uniquement des noms et des URL
# -----------------------------------------------------------------------------
az functionapp config appsettings set -n "$FUNC" -g "$RG" --settings \
  "STORAGE_ACCOUNT_NAME=$ST" \
  "COSMOS_URL=https://cosmos-$EQ.documents.azure.com:443/" \
  "COSMOS_DATABASE=pipeline" \
  "COSMOS_CONTAINER=inferences" \
  "API_URL=$API_URL" \
  "API_TIMEOUT_S=20" \
  "MAX_BLOB_BYTES=5242880" \
  "DASHBOARD_ORIGIN=https://$ST.z28.web.core.windows.net"

# -----------------------------------------------------------------------------
# 4. Deploiement du code
#    Par zip plutot qu'avec « func » : aucun outil supplementaire a installer.
#    --build-remote installe les dependances cote Azure ; le paquet construit
#    pese ~13 Mo alors que la source fait 6 Ko.
# -----------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp functions/function_app.py functions/host.json functions/requirements.txt "$TMP/"
(cd "$TMP" && zip -q -r package.zip function_app.py host.json requirements.txt)
az functionapp deployment source config-zip -n "$FUNC" -g "$RG" \
  --src "$TMP/package.zip" --build-remote true

# -----------------------------------------------------------------------------
# 5. Verification : les TROIS fonctions doivent apparaitre
#    Si la liste est vide, l'indexation a echoue. Chercher la cause dans
#    Application Insights, pas dans les logs de deploiement :
#      traces | where message has 'failed to index' or message has 'FunctionLoadError'
#    Piege rencontre : le parametre de la fonction HTTP doit s'appeler « req ».
#    @app.route n'accepte pas d'arg_name, contrairement a event_grid_trigger et
#    queue_trigger. Un autre nom fait echouer l'indexation des TROIS fonctions.
# -----------------------------------------------------------------------------
az functionapp function list -n "$FUNC" -g "$RG" \
  --query "[].{nom:name, declencheur:config.bindings[0].type}" -o table
