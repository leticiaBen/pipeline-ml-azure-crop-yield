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

**Crop Yield Prediction Dataset** — [Kaggle, auteur `patelris`](https://www.kaggle.com/datasets/patelris/crop-yield-prediction-dataset),
**version 7 épinglée** dans le script d'entraînement. Construit à partir de données **FAO**
(production et rendements) et **Banque mondiale** (climat).

- **Licence** : [World Bank Dataset Terms of Use](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets)
- **Volume** : 1,5 Mo pour `yield_df.csv`, très loin de la limite de 50 Mo de l'énoncé
- **Étendue** : 101 pays, 10 cultures, années 1990 à 2013
- **Lignes** : 28 242 brutes, **25 932** après déduplication

> La fusion des températures effectuée en amont par l'auteur a dupliqué **2 310 lignes**. Sans
> `drop_duplicates()`, ces doublons se répartiraient entre entraînement et test : le modèle serait
> évalué sur des lignes qu'il a déjà vues, et les scores seraient surévalués.

**Tâche** — régression : prédire `hg/ha_yield`, le rendement en hectogrammes par hectare
(diviser par 10 pour des kg/ha), à partir du pays, de la culture, de l'année, de la pluviométrie
annuelle, des pesticides utilisés et de la température moyenne.

**Protocole d'évaluation** — découpage **temporel** et non aléatoire : entraînement sur
21 305 lignes de 1990 à 2009, évaluation sur 4 627 lignes de 2010 à 2013, jamais vues.
Un découpage aléatoire mélangerait les années et laisserait le modèle « voir le futur » : les
scores seraient meilleurs, mais mensongers.

Cible entraînée en **logarithme**, les rendements moyens allant de 16 992 hg/ha pour le soja à
198 666 pour la pomme de terre, soit un facteur 12. Sans cette transformation, l'erreur
quadratique se concentrerait sur les cultures à fort rendement et le modèle négligerait les autres.

### Modèle — version 1.0.0

`HistGradientBoostingRegressor` (scikit-learn), graine fixée à 42. Choisi plutôt qu'une forêt
aléatoire, qui dépasserait sur ces données les 100 Mo interdits par l'énoncé.

| | RMSE | MAE | R² |
|---|---|---|---|
| Référence naïve (rendement moyen par culture) | 61 468 | 36 357 | 0.5835 |
| **Modèle 1.0.0** | **23 118** | **12 246** | **0.9411** |
| *Gain* | *−62.4 %* | *−66.3 %* | |

Unités en hg/ha. Le modèle réduit l'erreur absolue moyenne de **66 %** par rapport à la
référence naïve, et explique 94.1 % de la variance contre 58.4 % pour celle-ci.

### Contraintes de l'énoncé

| Contrainte | Seuil | Mesuré | |
|---|---|---|---|
| Taille du modèle | < 100 Mo | **0.531 Mo** | OK |
| Inférence sur CPU | < 1 s | **28.2 ms** à froid, 9.35 ms en médiane | OK |
| Chargement du modèle | — | 11.11 ms | |

Chiffres produits par [`model/train.py`](model/train.py) et enregistrés dans
[`model/metrics.json`](model/metrics.json), avec les versions exactes des bibliothèques utilisées.

**Reproductibilité vérifiée** : deux exécutions successives produisent un `model-1.0.0.joblib` de
même empreinte MD5 et des métriques identiques. Le temps d'inférence, lui, varie avec la charge de
la machine — il reste deux ordres de grandeur sous la limite.

Un cas limite réel à signaler : **le Soudan figure dans le jeu de test sans apparaître dans
l'entraînement**. L'encodeur ordinal le traduit en `NaN`, que HistGradientBoosting traite
nativement comme une valeur manquante, sans lever d'exception.

### Pourquoi la cible en logarithme

Décision arbitrée, pas recopiée : les deux variantes ont été entraînées et comparées
(`model/compare_cible.py`, reproductible).

Le modèle minimise une erreur quadratique exprimée en hg/ha. Or une erreur de 10 % vaut
22 707 hg/ha sur la pomme de terre contre 1 826 sur le soja : au carré, la première coûte
155 fois plus cher. Sans transformation, le modèle a donc intérêt à soigner les cultures à fort
rendement et à négliger les autres. Le logarithme ramène tout à des écarts relatifs, où 10 %
d'erreur pèse pareil quelle que soit la culture.

**Erreur globale — la cible brute est meilleure :**

| | RMSE | MAE |
|---|---|---|
| Sans logarithme | **20 102** | **11 534** |
| Avec logarithme | 23 118 | 12 246 |

**Erreur relative par culture (MAPE) — le logarithme est meilleur sur 8 cultures sur 10 :**

| Culture | Rendement moyen | Sans log | Avec log | Écart |
|---|---|---|---|---|
| Soja | 18 257 | 24,0 % | **16,4 %** | −7,6 |
| Sorgho | 22 424 | 39,3 % | **24,4 %** | **−14,9** |
| Blé | 33 926 | 19,3 % | **14,7 %** | −4,6 |
| Maïs | 46 673 | 28,0 % | **18,4 %** | −9,5 |
| Riz | 47 925 | 19,2 % | **14,3 %** | −4,9 |
| Plantains | 107 470 | 18,2 % | **14,6 %** | −3,5 |
| Ignames | 120 803 | **22,0 %** | 23,3 % | +1,3 |
| Patates douces | 136 090 | 17,6 % | **15,3 %** | −2,4 |
| Manioc | 177 341 | **20,6 %** | 20,2 % | −0,4 |
| Pomme de terre | 227 066 | **12,4 %** | 13,0 % | +0,6 |

**Décision : garder le logarithme.** L'erreur globale en hg/ha est dominée par les cultures à
fort rendement : elle récompense le modèle qui ne s'occupe que d'elles. Le sorgho passe de 39 %
à 24 % d'erreur relative, tandis que les deux cultures qui se dégradent — ignames et pomme de
terre, parmi les trois plus hauts rendements — perdent moins d'un point. Un modèle exploitable
sur les dix cultures vaut mieux qu'un spécialiste de la pomme de terre à la note globale
flatteuse.

À noter : les deux variantes écrasent largement la référence naïve (RMSE 61 468), donc
l'exigence de la section 4.1 est satisfaite dans les deux cas.

### Reproduire l'entraînement

```bash
cd model
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python train.py
```

### Fichiers de simulation

[`model/make_samples.py`](model/make_samples.py) produit, depuis le jeu de test, les fichiers à
déposer dans `input/` pour la démonstration :

| Dossier | Contenu | Chemin exercé |
|---|---|---|
| `samples/valid/` | 12 lots de 25 lignes, prélevés à intervalle régulier pour couvrir plusieurs pays et cultures | `output/` + Cosmos DB |
| `samples/invalid/` | colonne manquante, mauvaise extension, fichier vide | `rejected/` |
| `samples/poison/` | pluviométrie à −500 mm | 422 de l'API, 5 tentatives, file `-poison` |

Le rendement réel est conservé dans les lots valides : l'API l'ignore, mais le worker peut le
stocker, ce qui permet au tableau de bord de tracer la courbe « prédit contre réel » de la
section 4.4. `--lots 100` génère de quoi alimenter le test de charge en bonus.

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

### Image de l'API

Construite en local depuis [`api/Dockerfile`](api/Dockerfile), multi-étapes, `python:3.12-slim`,
utilisateur non root `apiuser` (uid 10001), `HEALTHCHECK` sans `curl`.

| Mesure | Local (Mac, arm64) | Runner CI (Ubuntu, amd64) |
|---|---|---|
| Système de fichiers du conteneur | **387 Mo** | **348 Mo** |
| Somme des couches | 411 Mo | — |
| Poussée au registre (compressée) | 112 Mo | 113 Mo |
| Limite de l'énoncé | 500 Mo | 500 Mo |

L'écart entre 387 et 348 Mo vient de l'architecture : les roues scientifiques compilées pour
arm64 sont plus volumineuses que celles pour amd64. Les deux passent largement.

> `docker images` affiche **522 Mo** pour cette image, ce qui semble dépasser la limite. C'est un
> artefact du magasin containerd de Docker Desktop, qui additionne les couches décompressées et
> les blobs compressés : 411 + 112 = 523. La taille réelle, mesurée par `du` à l'intérieur du
> conteneur, est de 387 Mo.

Une première version pesait 816 Mo. Trois réductions, par ordre de rendement :

| Action | Gain |
|---|---|
| Suppression des suites de tests des bibliothèques scientifiques | ~100 Mo |
| `strip --strip-unneeded` sur les bibliothèques natives (205 Mo de `.so`) | ~39 Mo |
| `uvicorn` sans l'extra `[standard]` (uvloop, httptools, watchfiles, websockets…) | ~30 Mo |
| `pip`, `setuptools`, `wheel` retirés de l'image finale | ~13 Mo |
| `pip install --no-compile` et suppression des `__pycache__` | ~5 Mo |

`binutils`, nécessaire à `strip`, reste dans l'étape de construction et ne pèse rien dans l'image
finale : c'est précisément l'intérêt du multi-étapes.

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

### Intégration continue

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) — déclenché sur push vers `main` et sur
pull request. Entièrement sur les runners GitHub : **aucune ressource Azure n'est touchée**, donc
aucun coût et aucun quota en jeu.

| Job | Étapes |
|---|---|
| `qualite` | `ruff check .` sur `api/` et `model/`, puis `pytest` (12 tests) |
| `image` | construction, trois contrôles, puis publication sur GHCR |

L'image est construite avec `load` et non `push` : elle reste locale au runner le temps des
contrôles et **n'est publiée qu'une fois validée**.

**Trois garde-fous automatisés**, pour que les exigences de l'énoncé soient vérifiées par la
machine et non par la mémoire :

| Contrôle | Seuil | Relevé par la CI |
|---|---|---|
| Taille du système de fichiers de l'image | < 500 Mo | 348 Mo |
| Utilisateur du conteneur | non root | `uid=10001` |
| Label `org.opencontainers.image.source` | l'URL du dépôt | conforme |
| Label `org.opencontainers.image.revision` | le SHA du commit | conforme |
| Test de fumée : `/health` | 200 | 200 |
| Test de fumée : `/predict` | 200 | `410147.94` hg/ha en 51,65 ms |
| Test de fumée : pluviométrie négative | 422 | 422 |

L'image porte les **labels OCI standards**. Celui qui compte est
`org.opencontainers.image.source` : c'est lui qui relie le paquet au dépôt sur GHCR, ce qui le
fait apparaître dans l'onglet *Packages* et affiche un lien vers le code sur sa page.
`org.opencontainers.image.revision` est renseigné depuis `github.sha`, de sorte qu'une image
récupérée du registre dit de quel commit elle vient — en plus de son étiquette. Les deux sont
vérifiés par la CI : si le label `source` disparaissait, le paquet redeviendrait orphelin sans
que personne ne s'en aperçoive.

Les étiquettes suivent l'énoncé — version **et** SHA du commit :

```
ghcr.io/leticiaben/pipeline-ml-azure-crop-yield/api:1.0.0
ghcr.io/leticiaben/pipeline-ml-azure-crop-yield/api:<sha>
```

Le nom est forcé en minuscules, GHCR refusant `leticiaBen` tel quel. Aucun secret n'est
nécessaire : le `GITHUB_TOKEN` fourni par la plateforme suffit, et la publication est
conditionnée à un push sur `main` — une pull request venant d'un fork n'a pas le droit d'écrire
dans le registre, et n'en a pas besoin.

### Le paquet GHCR est public, et vérifié

Container Apps pourra donc le tirer **sans aucun identifiant**, ce qui évite le secret de
registre qu'aurait imposé un paquet privé (section 6 de l'énoncé).

Vérifié non pas dans l'interface, mais par une requête **anonyme** au registre — exactement ce
que fera Container Apps :

| Vérification | Résultat |
|---|---|
| Manifeste de `:1.0.0` sans identifiants | HTTP 200 |
| Manifeste par SHA de commit | HTTP 200 |
| Étiquettes listables en anonyme | 6 |
| Taille distribuée | 114 Mo, 10 couches |
| Utilisateur déclaré dans l'image | `apiuser` |
| Plateforme | `linux/amd64` |

Les cinq labels OCI sont bien présents sur l'image publiée :

```
org.opencontainers.image.title       API de prediction du rendement agricole
org.opencontainers.image.description Inference du rendement agricole en hg/ha ...
org.opencontainers.image.source      https://github.com/leticiaBen/pipeline-ml-azure-crop-yield
org.opencontainers.image.version     1.0.0
org.opencontainers.image.revision    822dac531f81f845e97b86e043fac37a7fb70a09
```

> Note pratique : la visibilité d'un paquet GHCR **ne peut pas** être changée par l'API REST ni
> par `gh` — aucun endpoint ne l'expose. C'est une opération d'interface web uniquement, à faire
> depuis *Package settings* → *Danger Zone* → *Change visibility*.

**Reste à faire, et dans cet ordre imposé :** l'abonnement Event Grid ne peut être créé qu'après
le premier déploiement du code Functions. Les attributions de rôles de la Function App
(Storage Blob Data Owner, Storage Queue Data Contributor, Cosmos DB Built-in Data Contributor)
attendent que celle-ci existe et devront être appliquées par la propriétaire de l'abonnement :
l'identité GitHub, simple Contributor, ne peut pas créer d'attributions de rôles. Commandes
préparées dans [`infra/03-roles.sh`](infra/03-roles.sh).

## 5. Exemple d'appel

L'API n'est pas encore déployée ; les exemples ci-dessous viennent de l'image Docker exécutée en
local, et seront repris tels quels avec l'URL publique une fois Container Apps en place.

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"Area":"France","Item":"Potatoes","Year":2012,
       "average_rain_fall_mm_per_year":867,"pesticides_tonnes":72000,"avg_temp":11.2}'
```

```json
{"predicted_yield_hg_ha": 410147.94, "model_version": "1.0.0", "inference_ms": 3.77}
```

Les quatre points de terminaison, relevés sur le conteneur :

| Appel | Réponse |
|---|---|
| `GET /health` | `{"status":"ok","model_loaded":true,"model_load_ms":1511.79,"model_version":"1.0.0","error":null}` |
| `GET /version` | `{"api_version":"1.0.0","model_version":"1.0.0"}` |
| `GET /metrics` | `{"total_calls":9,"predictions":6,"errors":3,"avg_latency_ms":20.78,...}` |

### Le rejet qui alimente la file poison

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"Area":"France","Item":"Potatoes","Year":2012,
       "average_rain_fall_mm_per_year":-500,"pesticides_tonnes":72000,"avg_temp":11.2}'
```

```json
{"detail":[{"type":"greater_than_equal",
            "loc":["body","average_rain_fall_mm_per_year"],
            "msg":"Input should be greater than or equal to 0",
            "input":-500,"ctx":{"ge":0.0}}]}
```

**HTTP 422.** C'est ce code qui déclenchera les 5 tentatives du worker puis l'envoi dans
`inference-requests-poison`. Les trois lignes de `samples/poison/pluie_negative.csv` ont été
passées à l'API conteneurisée : les trois renvoient 422.

### Prédit contre réel sur un vrai lot

Six premières lignes de `samples/valid/batch_001.csv`, envoyées au conteneur :

| Pays | Culture | Année | Réel | Prédit | Écart |
|---|---|---|---|---|---|
| Albania | Maize | 2010 | 66 790 | 58 645 | −12 % |
| Albania | Potatoes | 2010 | 231 111 | 160 434 | −31 % |
| Albania | Soybeans | 2010 | 16 667 | 19 003 | +14 % |
| Albania | Wheat | 2010 | 39 905 | 34 653 | −13 % |
| Albania | Maize | 2011 | 59 869 | 58 645 | −2 % |
| Albania | Potatoes | 2011 | 242 211 | 160 434 | −34 % |

La pomme de terre albanaise est nettement sous-estimée, et c'est instructif : son rendement a
fortement progressé après 2009, or le modèle n'a appris que sur 1990-2009. C'est la limite
assumée du découpage temporel — le modèle ne peut pas extrapoler une tendance qu'il n'a pas vue.
Un découpage aléatoire masquerait ce défaut en lui donnant des années postérieures à apprendre.


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
