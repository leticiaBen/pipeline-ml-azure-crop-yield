# Pipeline de Machine Learning événementiel sur Azure

**Prédiction du rendement agricole** à partir de la pluviométrie, de la température et de l'usage de pesticides.

ECE Paris — *Systèmes distribués et IA*, groupe Intelligence artificielle — Projet de synthèse 2026–2027.

Un fichier CSV déposé dans Blob Storage est validé, mis en file d'attente, envoyé à une API de ML
conteneurisée, puis son résultat est stocké et affiché dans un tableau de bord. L'ensemble est
supervisé, déployé automatiquement depuis GitHub et reste sous les 25 $ de budget.

---

## 1. Architecture

<!-- À compléter : schéma d'architecture (docs/architecture.png) -->

```
Blob input/ → Event Grid → Function dispatcher → Storage Queue ─┐
                                 │ (invalide)                   │ (+ file -poison)
                                 ↓                              ↓
                          Blob rejected/                 Function worker
                                                                │
                                           ┌────────────────────┼────────────────────┐
                                           ↓                    ↓                    ↓
                                  API ML (Container Apps)  Blob output/        Cosmos DB
                                     POST /predict                                   │
                                                                                      ↓
                                                        Function HTTP /api/recent → Dashboard ($web)
```

Transverse : Application Insights (OpenTelemetry), GitHub Actions (CI/CD), identité managée, budget et alertes.

| # | Service | Rôle |
|---|---|---|
| 1 | Blob Storage | Conteneurs `input/`, `output/`, `rejected/`, `models/`, versionnage activé |
| 2 | Event Grid + `dispatcher` | Réagit à `Microsoft.Storage.BlobCreated` sur `input/`, valide ou rejette |
| 3 | Storage Queue | `inference-requests` ; 5 tentatives puis `inference-requests-poison` |
| 4 | Function `worker` | Consomme la file, appelle l'API, écrit le résultat, émet les métriques |
| 5 | API ML | FastAPI conteneurisée sur Container Apps, 0 à 2 réplicas |
| 6 | Blob `output/` | Résultat JSON complet de chaque inférence |
| 7 | Cosmos DB | Métadonnées : fichier, prédiction, version du modèle, durée |
| 8 | Tableau de bord | Page statique `$web` + Chart.js, Function HTTP `/api/recent` |

> Les trois fonctions (`dispatcher`, `worker`, `recent`) vivent dans **une seule Function App**
> Python 3.12 (modèle v2, `functions/function_app.py`) : sur le plan Flex Consumption, un plan ne
> contient qu'une seule application.

## 2. Région Azure : choix et justification

**Région retenue : `francecentral`.** Abonnement d'intégration : Azure for Students de
[@leticiaBen](https://github.com/leticiaBen), tenant Groupe INSEEC (POCE). C'est ce crédit qui
porte l'enveloppe de 25 $.

### Démarche

La politique de l'abonnement n'autorise que 5 régions (`Allowed resource deployment regions`) :

```
francecentral · denmarkeast · norwayeast · polandcentral · austriaeast
```

Chacune a été confrontée aux trois services dont le projet dépend :

| Région | Flex Consumption | Container Apps | Cosmos DB | Verdict |
|---|---|---|---|---|
| **francecentral** | oui | oui | oui | **retenue** |
| denmarkeast | **non** | non | oui | éliminée |
| norwayeast | oui | oui | oui | repli 1 |
| polandcentral | oui | oui | oui | repli 2 |
| austriaeast | oui | oui | oui | repli 3 |

`denmarkeast` est écartée faute de Flex Consumption, que l'énoncé impose pour la Function App.

### Pourquoi `francecentral` parmi les quatre restantes

**Le coût.** Prix relevés sur l'API publique des tarifs Azure, en euros :

| Poste | francecentral | norwayeast | polandcentral | austriaeast |
|---|---|---|---|---|
| Stockage Hot LRS (Go/mois) | **0,0172** | 0,0194 | 0,0176 | 0,0176 |
| Ingestion de logs (Go) | **0,5611** | 0,6419 | 0,5835 | 0,5835 |
| Container Apps vCPU + mémoire | 0,00 | 0,00 | 0,00 | 0,00 |
| Container Apps requêtes (par million) | 0,3591 | 0,3591 | 0,3591 | 0,3591 |

`francecentral` est la moins chère sur les deux seuls postes qui peuvent être facturés ici. Le
stockage Cosmos DB y est en revanche le plus cher des quatre (0,2805 contre 0,2244 €/Go/mois en
`austriaeast`), mais le Free Tier offre 25 Go à vie et le projet n'en stockera que quelques
mégaoctets : ce tarif ne sera jamais appliqué. Les écarts restent de l'ordre du centime sur
15 jours — la région ne détermine pas le budget.

**La disponibilité.** C'est la plus mature des quatre, donc la moins susceptible de refuser une
création pour cause de capacité, ce que l'énoncé signale comme l'échec le plus fréquent sur
Cosmos DB. Les trois autres sont des régions récentes.

**La preuve empirique.** L'abonnement y héberge déjà trois groupes de ressources déployés avec
succès, ce qui démontre que la région fonctionne réellement sur ce compte — là où les autres
n'auraient été qu'un pari. La création de Cosmos DB a d'ailleurs abouti en 1 min 37 sans aucun
refus de capacité.

**La latence** depuis Paris, accessoire mais utile pour la démonstration en direct.

## 3. Jeu de données et modèle

**Crop Yield Prediction Dataset** — Kaggle, auteur `patelris`, à partir de données **FAO** et
**Banque mondiale**. Environ 28 000 lignes, une centaine de pays, 10 cultures, années 1990 à 2013.
Taille ≈ 2 Mo (limite de l'énoncé : 50 Mo).

- **Licence** : *à recopier depuis la page Kaggle du jeu de données*
- **Sources d'origine** : FAO (production et rendements), Banque mondiale (climat)

**Tâche** — régression : prédire `hg/ha_yield`, le rendement en hectogrammes par hectare
(diviser par 10 pour des kg/ha), à partir du pays, de la culture, de l'année, de la pluviométrie
annuelle, des pesticides utilisés et de la température moyenne.

**Protocole d'évaluation** — découpage **temporel** et non aléatoire : entraînement sur 1990–2009,
test sur 2010–2013. Un découpage aléatoire laisserait le modèle « voir le futur » et gonflerait
artificiellement les scores. Cible entraînée en logarithme, les rendements variant d'un facteur 10
entre cultures (pomme de terre contre blé).

### Modèle — version 1.0.0

`HistGradientBoostingRegressor` (scikit-learn), graine fixée à 42.

| | RMSE | MAE | R² |
|---|---|---|---|
| Référence naïve (rendement moyen par culture) | *à compléter* | *à compléter* | *à compléter* |
| Modèle 1.0.0 | *à compléter* | *à compléter* | *à compléter* |

| Contrainte de l'énoncé | Mesuré |
|---|---|
| Taille < 100 Mo | *à compléter* |
| Inférence < 1 s sur CPU | *à compléter* |

## 4. Déploiement pas à pas

<!-- À compléter : prérequis, premier déploiement du code, abonnement Event Grid, attributions de rôles -->

### Socle déjà déployé

Script reproductible et commenté : [`infra/01-socle.sh`](infra/01-socle.sh).

| Ressource | Nom | Détail |
|---|---|---|
| Groupe de ressources | `rg-projet-cropyield` | étiquettes `projet=dscc`, `equipe=cropyield` |
| Cosmos DB | `cosmos-cropyield` | Free Tier actif, base `pipeline` à 400 RU/s, conteneur `inferences` clé `/fileName` |
| Stockage | `stcropyieldpipe` | TLS 1.2, accès blob anonyme désactivé, versionnage activé |
| — conteneurs | | `input`, `output`, `rejected`, `models`, `$web` |
| — file d'attente | | `inference-requests` (la file `-poison` est créée par le runtime au 5ᵉ échec) |
| Log Analytics | `log-cropyield` | plafond **0,2 Go/jour**, rétention 30 jours |
| Application Insights | `appi-cropyield` | adossé à `log-cropyield`, dans le groupe du projet |
| Container Apps | `cae-cropyield` | un seul environnement, journaux vers `log-cropyield` |
| Identité managée | `id-github-cropyield` | OIDC, sujet `repo:leticiaBen/pipeline-ml-azure-crop-yield:environment:production` |
| Budget | `budget-projet-cropyield` | 25 $/mois, alertes à 20, 50 et 80 % |
| Attribution de rôle | — | `id-github-cropyield` → **Contributor sur le seul groupe**, aucune attribution au niveau abonnement |

Tableau de bord (encore vide) : `https://stcropyieldpipe.z28.web.core.windows.net/`

### Secrets GitHub

Trois identifiants, enregistrés **sur l'environnement `production`** et non à l'échelle du dépôt :

| Secret | Contenu |
|---|---|
| `AZURE_CLIENT_ID` | clientId de l'identité managée `id-github-cropyield` |
| `AZURE_TENANT_ID` | tenant de l'abonnement |
| `AZURE_SUBSCRIPTION_ID` | abonnement d'intégration |

Ce sont des identifiants non sensibles, comme l'autorise la section 4.6 : l'authentification se
fait par OIDC, donc aucun mot de passe, aucune clé, aucune chaîne de connexion ne transite ni ne
séjourne dans GitHub. Le dépôt n'a **aucun secret à l'échelle du dépôt** — les portées
d'environnement font que seul un job déclarant `environment: production` peut les lire, ce qui
double la porte d'approbation d'une porte de visibilité. `ci.yml` n'y a pas accès, et n'en a pas
besoin.

**Reste à faire, et dans cet ordre imposé :** l'abonnement Event Grid ne peut être créé qu'après
le premier déploiement du code Functions. Les attributions de rôles de la Function App
(Storage Blob Data Owner, Storage Queue Data Contributor, Cosmos DB Built-in Data Contributor)
attendent que celle-ci existe et devront être appliquées par la propriétaire de l'abonnement :
l'identité GitHub, simple Contributor, ne peut pas créer d'attributions de rôles. Commandes
préparées dans [`infra/03-roles.sh`](infra/03-roles.sh).

## 5. Exemple d'appel

<!-- À compléter : curl https://<api>/predict -d '{...}' et la réponse -->

## 6. Exemple d'événement Event Grid et de message de file

<!-- À compléter : payload BlobCreated reçu par le dispatcher + message JSON publié dans la file -->

## 7. Requêtes KQL

<!-- À compléter : 3 requêtes + captures d'écran (inférences par heure, 5 fichiers les plus lents, répartition des erreurs) -->

## 8. Restrictions Azure for Students rencontrées

| Restriction | Ce que nous avons vu | Solution appliquée |
|---|---|---|
| Dépôt GitHub privé : relecteurs obligatoires indisponibles | Règle absente des offres Free, Pro et Team ; le sujet OIDC `environment:production` devenait inutilisable | Dépôt passé en **public**, environnement `production` avec 5 relecteurs, auto-approbation interdite, contournement administrateur désactivé |
| Régions imposées (5 pour cet abonnement) | `Allowed resource deployment regions` : francecentral, denmarkeast, norwayeast, polandcentral, austriaeast | Croisement avec `az functionapp list-flexconsumption-locations` : `denmarkeast` éliminée, `francecentral` retenue (section 2) |
| Un seul Cosmos DB Free Tier par abonnement | Vérifié avant création : aucun compte Cosmos existant, le Free Tier était disponible | Compte créé avec `--enable-free-tier true` dès la première commande, l'option ne pouvant pas être ajoutée après coup |
| Un seul environnement Container Apps | Quota vérifié avant création : aucun environnement existant | Un unique environnement `cae-cropyield` ; staging et production seront deux applications ou deux révisions dedans |
| Aucun droit d'administration Entra ID | — | Déploiement par identité managée attribuée par l'utilisateur et informations d'identification fédérées : aucune app registration, aucun service principal, aucun secret Azure dans GitHub |
| `DefaultResourceGroup-*` préexistant | Un `DefaultResourceGroup-PAR` subsiste d'un TP antérieur | Espace Log Analytics créé explicitement dans le groupe du projet pour ne pas en générer un nouveau ; celui qui existe sera traité avant la preuve de suppression finale |
| *à compléter au fil du projet* | | |

## 9. Structure du dépôt

| Dossier | Contenu |
|---|---|
| `model/` | Script d'entraînement, `requirements.txt` figé, modèle versionné |
| `api/` | API FastAPI d'inférence, Dockerfile multi-étapes, tests pytest |
| `functions/` | `function_app.py` (dispatcher, worker, recent), `host.json`, `requirements.txt` |
| `web/` | Tableau de bord statique (HTML/JS + Chart.js) |
| `infra/` | Script `az` commenté de création du socle |
| `docs/` | Schéma d'architecture, captures, rapport de coûts, journal de temps |
| `.github/workflows/` | `ci.yml` (lint, tests, image GHCR), `deploy.yml` (OIDC → Azure) |

## 10. Équipe

Cinq membres. L'énoncé prévoit des équipes de 3 (recommandé) ou 4 : effectif à confirmer
auprès de l'enseignante.

| Membre | Partie présentée en soutenance |
|---|---|
| [@leticiaBen](https://github.com/leticiaBen) | *à répartir* |
| [@NourMontacer01](https://github.com/NourMontacer01) | *à répartir* |
| [@Essid01](https://github.com/Essid01) | *à répartir* |
| [@Yacine-BJ](https://github.com/Yacine-BJ) | *à répartir* |
| [@hibabouchaala](https://github.com/hibabouchaala) | *à répartir* |

Les cinq sont relecteurs de l'environnement `production` : un déploiement vers Azure doit être
approuvé par un membre **autre** que l'auteur du commit (`prevent_self_review`), et les
administrateurs ne peuvent pas contourner la porte (`can_admins_bypass: false`).

Un membre détient l'**abonnement d'intégration** (celui qui porte l'enveloppe de 25 $) ; les
autres travaillent en local avec Docker, Azure Functions Core Tools et Azurite, et déploient
par la CI/CD sans accès Azure personnel.

## 11. Budget

Enveloppe maximale : **25 $** sur le crédit de l'abonnement d'intégration (coût réel visé : < 5 $).
Étiquettes `projet=dscc` et `equipe=<nom>` sur le groupe de ressources, budget avec alertes à
20, 50 et 80 %. Rapport de coûts dans `docs/`.
