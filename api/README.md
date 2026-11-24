# api

API REST d'inférence, conteneurisée et déployée sur Azure Container Apps (section 4.2 de l'énoncé).

FastAPI (Python 3.12) avec validation Pydantic — c'est elle qui refuse les valeurs aberrantes
(pluviométrie négative) avec un code **422**, ce qui déclenche les reprises puis la file `-poison`.

| Endpoint | Rôle |
|---|---|
| `GET /health` | État du service et temps de chargement du modèle |
| `GET /version` | Versions de l'API et du modèle |
| `POST /predict` | Prédiction du rendement (hg/ha) pour une ligne |
| `GET /metrics` | Nombre d'appels et latence moyenne |

À fournir : au moins 3 tests pytest (succès, entrée invalide 422, corps absent), Dockerfile
multi-étapes sur `python:3.12-slim`, utilisateur non root, image < 500 Mo, `HEALTHCHECK`,
télémétrie via `azure-monitor-opentelemetry`.

Déploiement : 0,25 vCPU / 0,5 Gio, `min-replicas 0`, `max-replicas 2`, sondes liveness et
readiness sur `/health`, configuration uniquement par variables d'environnement.
