#!/usr/bin/env bash
# =============================================================================
#  Socle Azure du projet — Pipeline de ML événementiel
#  ECE Paris, Systèmes distribués et IA. Référence : énoncé sections 3.2 et 6.
#
#  Idempotent : relancer le script ne casse rien (les créations existantes
#  renvoient la ressource en place).
#
#  Ce qui N'EST PAS ici, volontairement :
#    - l'abonnement Event Grid : il échoue tant que la fonction dispatcher
#      n'est pas déployée (validation du point de terminaison) → 02-eventgrid.sh
#    - les attributions de rôles : elles touchent aux permissions et doivent
#      être appliquées sciemment par le propriétaire de l'abonnement
#      → 03-roles.sh
# =============================================================================
set -euo pipefail

EQ=cropyield                    # nom d'équipe (minuscules, sans tiret)
LOC=francecentral               # voir la justification dans le README, section 2
RG=rg-projet-$EQ
ST=st${EQ}pipe                  # stockage : global, minuscules, <= 24 caractères
COSMOS=cosmos-$EQ
ENV=cae-$EQ
FUNC=func-$EQ
ID=id-github-$EQ
LAW=log-$EQ
AI=appi-$EQ
REPO="leticiaBen/pipeline-ml-azure-crop-yield"
MAIL="<adresse-de-notification>"   # destinataire des alertes de budget

# -----------------------------------------------------------------------------
# 0. Vérifier la région AVANT de créer quoi que ce soit (énoncé 3.2)
#    La région doit figurer dans les DEUX listes.
# -----------------------------------------------------------------------------
# Régions autorisées par la politique de l'abonnement :
#   az policy assignment list --disable-scope-strict-match \
#     --query "[].{nom:displayName, params:parameters}" -o json
#   → francecentral, denmarkeast, norwayeast, polandcentral, austriaeast
#
# Régions où Flex Consumption existe :
#   az functionapp list-flexconsumption-locations -o table
#   → denmarkeast absente, les 4 autres présentes
#
# Fournisseurs à enregistrer une fois par abonnement (déjà fait ici) :
#   for p in Microsoft.Web Microsoft.App Microsoft.EventGrid Microsoft.DocumentDB \
#            Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity; do
#     az provider register --namespace $p
#   done

# -----------------------------------------------------------------------------
# 1. Groupe de ressources — les étiquettes sont exigées par la section 4.7
# -----------------------------------------------------------------------------
az group create -n "$RG" -l "$LOC" --tags projet=dscc equipe=$EQ

# -----------------------------------------------------------------------------
# 2. Cosmos DB EN PREMIER (énoncé 3.2)
#    C'est le service le plus souvent refusé faute de capacité : le créer
#    d'abord valide la région au plus tôt. En cas de refus, changer de région
#    autorisée AVANT toute autre chose et le noter dans le journal de temps.
#    Le Free Tier se choisit à la création et ne peut pas être ajouté ensuite.
#    Un seul compte Free Tier par abonnement.
# -----------------------------------------------------------------------------
az cosmosdb create -n "$COSMOS" -g "$RG" --enable-free-tier true \
  --locations regionName="$LOC" failoverPriority=0 isZoneRedundant=False

# 400 RU/s partagés au niveau de la base (le Free Tier couvre 1000 RU/s)
az cosmosdb sql database create -a "$COSMOS" -g "$RG" -n pipeline --throughput 400
az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d pipeline \
  -n inferences --partition-key-path /fileName

# -----------------------------------------------------------------------------
# 3. Stockage : conteneurs, file d'attente, site web statique
#    allow-blob-public-access false : les blobs ne sont pas lisibles
#    anonymement. Le site $web reste accessible, son point de terminaison web
#    est public par conception.
# -----------------------------------------------------------------------------
az storage account create -n "$ST" -g "$RG" -l "$LOC" --sku Standard_LRS \
  --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false

# Versionnage des blobs, exigé par la section 2 de l'énoncé
az storage account blob-service-properties update --account-name "$ST" -g "$RG" \
  --enable-versioning true

for c in input output rejected models; do
  az storage container create --account-name "$ST" -n $c
done

# La file -poison (inference-requests-poison) est créée automatiquement par le
# runtime Functions au 5e échec : ne pas la créer à la main.
az storage queue create --account-name "$ST" -n inference-requests

az storage blob service-properties update --account-name "$ST" \
  --static-website --index-document index.html --404-document index.html

# -----------------------------------------------------------------------------
# 4. SUPERVISION AVANT LE RESTE (énoncé 4.5)
#    Sans espace de travail créé explicitement ici, la CLI en crée un sans
#    plafond, éventuellement hors du groupe, qui survivrait à sa suppression.
#    C'est l'origine des groupes DefaultResourceGroup-* qui traînent.
# -----------------------------------------------------------------------------
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOC" --quota 0.2

LAW_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query id -o tsv)
az monitor app-insights component create --app "$AI" -g "$RG" -l "$LOC" --workspace "$LAW_ID"

# -----------------------------------------------------------------------------
# 5. Container Apps : UN SEUL environnement (quota étudiant)
#    Compter 8 à 10 minutes : l'environnement provisionne tout un plan de
#    contrôle managé. Déployer une application dedans ne prend ensuite que
#    quelques secondes.
# -----------------------------------------------------------------------------
az containerapp env create -n "$ENV" -g "$RG" -l "$LOC" \
  --logs-workspace-id "$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" \
      --query customerId -o tsv)" \
  --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys -g "$RG" \
      -n "$LAW" --query primarySharedKey -o tsv)"

# -----------------------------------------------------------------------------
# 6. Identité managée pour GitHub Actions (OIDC, aucun secret Azure)
#    Aucun droit Entra ID nécessaire : pas d'app registration, pas de service
#    principal.
#
#    PIÈGE zsh : écrire "repo:$REPO:environment:production" produit
#    "repo:nvironment:production", parce que zsh interprète $REPO:e comme le
#    modificateur d'historique « extension du nom de fichier », qui est vide.
#    Les accolades ${REPO} sont obligatoires. Un sujet erroné donne
#    AADSTS700213 au moment du déploiement.
# -----------------------------------------------------------------------------
az identity create -n "$ID" -g "$RG"

az identity federated-credential create -n github-production \
  --identity-name "$ID" -g "$RG" \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${REPO}:environment:production" \
  --audiences api://AzureADTokenExchange

# Vérifier le sujet, c'est l'erreur la plus coûteuse à diagnostiquer plus tard
az identity federated-credential show -n github-production \
  --identity-name "$ID" -g "$RG" --query subject -o tsv

# -----------------------------------------------------------------------------
# 7. Budget 25 $ sur le groupe, alertes à 20, 50 et 80 % (énoncé 4.7)
#    Note : le champ thresholdType n'est pas accepté par az 2.92 ; il est
#    omis, la valeur par défaut « Actual » convient.
# -----------------------------------------------------------------------------
cat > /tmp/budget-notifications.json <<EOF
{
  "Alerte20": { "enabled": true, "operator": "GreaterThanOrEqualTo", "threshold": 20, "contactEmails": ["$MAIL"] },
  "Alerte50": { "enabled": true, "operator": "GreaterThanOrEqualTo", "threshold": 50, "contactEmails": ["$MAIL"] },
  "Alerte80": { "enabled": true, "operator": "GreaterThanOrEqualTo", "threshold": 80, "contactEmails": ["$MAIL"] }
}
EOF
cat > /tmp/budget-periode.json <<'EOF'
{ "startDate": "2026-11-01T00:00:00Z", "endDate": "2027-06-30T00:00:00Z" }
EOF
az consumption budget create-with-rg -g "$RG" -n "budget-projet-$EQ" \
  --amount 25 --category Cost --time-grain Monthly \
  --time-period @/tmp/budget-periode.json \
  --notifications @/tmp/budget-notifications.json
rm -f /tmp/budget-notifications.json /tmp/budget-periode.json

# -----------------------------------------------------------------------------
# 8. Vérification finale
# -----------------------------------------------------------------------------
az resource list -g "$RG" --query "[].{nom:name,type:type,region:location}" -o table
echo "Point de terminaison du tableau de bord :"
az storage account show -n "$ST" -g "$RG" --query primaryEndpoints.web -o tsv
