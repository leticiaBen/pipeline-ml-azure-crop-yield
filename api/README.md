# api

API REST d'inférence du rendement agricole — section 4.2 de l'énoncé.

FastAPI (Python 3.12), validation Pydantic, conteneurisée et destinée à Azure
Container Apps avec 0,25 vCPU / 0,5 Gio et `min-replicas 0`.

## Points de terminaison

| Endpoint | Rôle |
|---|---|
| `GET /health` | état du service et **temps de chargement du modèle** |
| `GET /version` | versions de l'API et du modèle |
| `POST /predict` | prédiction du rendement pour une ligne de relevé |
| `GET /metrics` | nombre d'appels, erreurs et latence moyenne |

### Exemple

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"Area":"France","Item":"Potatoes","Year":2012,
       "average_rain_fall_mm_per_year":867,"pesticides_tonnes":72000,"avg_temp":11.2}'
```

```json
{"predicted_yield_hg_ha": 410147.94, "model_version": "1.0.0", "inference_ms": 59.5}
```

## La validation, et son rôle dans le pipeline

C'est Pydantic qui refuse les valeurs physiquement impossibles :

| Champ | Borne |
|---|---|
| `average_rain_fall_mm_per_year` | 0 à 20 000 mm |
| `pesticides_tonnes` | ≥ 0 |
| `avg_temp` | −50 à 60 °C |
| `Year` | 1900 à 2100 |

Une pluviométrie négative renvoie donc **422**, et c'est voulu : le worker
réessaie 5 fois, puis le message part dans `inference-requests-poison`. C'est
le troisième chemin que la vidéo de démonstration doit montrer.

Les champs inconnus sont ignorés, dont `hg/ha_yield` — le rendement réel que
les CSV de simulation conservent pour le tableau de bord. Un test vérifie que
sa présence ne change pas la prédiction.

## Configuration

Uniquement par variables d'environnement, comme l'exige l'énoncé :

| Variable | Défaut | Rôle |
|---|---|---|
| `MODEL_PATH` | `/app/model/model-1.0.0.joblib` | modèle sérialisé |
| `MODEL_VERSION` | `1.0.0` | version annoncée par `/version` |
| `API_VERSION` | `1.0.0` | version de l'API |
| `PORT` | `8000` | port d'écoute |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | télémétrie, **optionnelle** |

Sans chaîne de connexion, la télémétrie est inerte et l'API tourne en local
sans aucune dépendance Azure. Avec, elle émet les deux métriques
personnalisées de la section 4.5 : `inferences_total` et `model_latency_ms`.

## Lancer en local

```bash
cd api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
MODEL_PATH=../model/model-1.0.0.joblib uvicorn main:app --reload
```

## Tests

```bash
cd api && ./.venv/bin/python -m pytest -q
```

Les tests chargent le **vrai** modèle versionné de `model/`, pas une
imitation. L'énoncé en exige trois ; il y en a douze :

| Test | Vérifie |
|---|---|
| `test_predict_succes` | 200, version du modèle, ordre de grandeur du rendement |
| `test_predict_entree_invalide_422` | pluviométrie négative rejetée, et sur le bon champ |
| `test_predict_corps_absent` | 422 sans corps de requête |
| `test_health` | `model_loaded` et temps de chargement non nul |
| `test_version` | les deux versions exactement |
| `test_metrics_compte_les_appels` | incrémentation et latence moyenne |
| `test_metrics_compte_aussi_les_rejets` | un 422 compte comme appel et comme erreur |
| `test_champ_manquant_422` | champ absent |
| `test_type_invalide_422` | mauvais type |
| `test_temperature_absurde_422` | borne haute de température |
| `test_rendement_reel_ignore` | `hg/ha_yield` ignoré, prédiction inchangée |
| `test_pays_inconnu_ne_plante_pas` | pays jamais vu absorbé via NaN |

## Image Docker

Multi-étapes, `python:3.12-slim`, utilisateur non root `apiuser` (uid 10001),
`HEALTHCHECK` sans `curl` — l'image slim n'en contient pas, `urllib` suffit.

Le contexte de construction est la **racine du dépôt**, car l'image embarque
aussi le modèle de `model/` :

```bash
docker build -f api/Dockerfile -t crop-yield-api:1.0.0 .
docker run --rm -p 8000:8000 crop-yield-api:1.0.0
```

Le `.dockerignore` de la racine ramène le contexte de 690 Mo à **0,8 Mo** en
excluant les environnements virtuels et les données.

## Taille de l'image

| Mesure | Valeur |
|---|---|
| Système de fichiers du conteneur (`du` interne) | **387 Mo** |
| Somme des couches (`docker history`) | **411 Mo** |
| Compressée, telle que poussée sur GHCR | **112 Mo** |
| Limite de l'énoncé | 500 Mo |

Attention : `docker images` annonce **522 Mo**. Le magasin containerd de Docker Desktop
additionne les couches décompressées et les blobs compressés (411 + 112 = 523). Les trois
mesures ci-dessus sont cohérentes entre elles et toutes sous la limite.

La première version naïve pesait 816 Mo. Détail des réductions dans la section 4 du README
racine.

## Vérifications effectuées sur le conteneur

| Point | Résultat |
|---|---|
| Utilisateur | `uid=10001(apiuser)` — non root |
| `HEALTHCHECK` Docker | `healthy` après 5 vérifications |
| Chargement du modèle | 1 511 ms à froid, d'où `--start-period=20s` |
| Inférence | 82 ms au premier appel, 3,8 ms ensuite |
| `samples/valid/batch_001.csv` | 6 lignes prédites |
| `samples/poison/pluie_negative.csv` | 3 lignes, 3 × HTTP 422 |
