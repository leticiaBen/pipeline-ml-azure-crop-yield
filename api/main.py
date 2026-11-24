"""
API d'inférence du rendement agricole — section 4.2 de l'énoncé.

Quatre points de terminaison :
  GET  /health   état du service et temps de chargement du modèle
  GET  /version  versions de l'API et du modèle
  POST /predict  prédiction du rendement pour une ligne
  GET  /metrics  nombre d'appels et latence moyenne

Configuration **uniquement** par variables d'environnement, comme l'exige
l'énoncé pour le déploiement sur Container Apps :
  MODEL_PATH                                chemin du modèle sérialisé
  MODEL_VERSION                             version du modèle servie
  API_VERSION                               version de cette API
  APPLICATIONINSIGHTS_CONNECTION_STRING     télémétrie (optionnelle)
"""

import os
import threading
import time
from contextlib import asynccontextmanager

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

API_VERSION = os.getenv("API_VERSION", "1.0.0")
MODEL_VERSION = os.getenv("MODEL_VERSION", "1.0.0")
MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/model-1.0.0.joblib")
# Commit qui a produit l'image en cours d'execution. Renseigne par deploy.yml.
# Sans lui, le critere « un commit sur main met a jour l'API de production,
# visible via GET /version » (section 4.6) ne serait pas verifiable : ni
# api_version ni model_version ne changent d'un commit a l'autre.
GIT_SHA = os.getenv("GIT_SHA", "inconnu")

# Ordre imposé par le pipeline entraîné : ne pas réarranger.
FEATURES = ["Area", "Item", "Year", "average_rain_fall_mm_per_year",
            "pesticides_tonnes", "avg_temp"]

# --------------------------------------------------------------------------
# Télémétrie Azure Monitor OpenTelemetry (section 4.2), et les deux métriques
# personnalisées de la section 4.5. Tout est optionnel : sans chaîne de
# connexion, les compteurs sont des objets inertes et l'API tourne en local
# sans aucune dépendance Azure.
# --------------------------------------------------------------------------
_compteur_inferences = None
_histogramme_latence = None


def _configurer_telemetrie(app: FastAPI) -> None:
    global _compteur_inferences, _histogramme_latence
    chaine = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not chaine:
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry import metrics

        configure_azure_monitor(connection_string=chaine)
        metre = metrics.get_meter("crop-yield-api")
        _compteur_inferences = metre.create_counter(
            "inferences_total", unit="1", description="Nombre d'inférences servies")
        _histogramme_latence = metre.create_histogram(
            "model_latency_ms", unit="ms", description="Latence du modèle")
    except Exception as e:
        # Une télémétrie cassée ne doit jamais empêcher l'API de servir.
        print(f"Télémétrie non configurée : {e}")


# --------------------------------------------------------------------------
# État du service
# --------------------------------------------------------------------------
class Etat:
    def __init__(self) -> None:
        self.modele = None
        self.chargement_ms: float | None = None
        self.erreur_chargement: str | None = None
        self.appels = 0
        self.predictions = 0
        self.erreurs = 0
        self.latence_totale_ms = 0.0
        self.verrou = threading.Lock()


etat = Etat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    try:
        etat.modele = joblib.load(MODEL_PATH)
        etat.chargement_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as e:
        # On ne fait pas échouer le démarrage : /health doit pouvoir
        # répondre et signaler le problème, sinon les sondes de
        # Container Apps ne diagnostiquent rien.
        etat.erreur_chargement = f"{type(e).__name__}: {e}"
    _configurer_telemetrie(app)
    yield


app = FastAPI(
    title="API de prédiction du rendement agricole",
    version=API_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def compter_les_appels(requete, suivant):
    """Compte TOUS les appels à /predict, y compris ceux que Pydantic rejette.

    Sans ce middleware, une entrée invalide n'apparaîtrait pas dans /metrics :
    la validation échoue avant que la fonction predict ne soit exécutée. Or
    l'énoncé demande le nombre d'appels, et les rejets 422 font partie du
    trafic réel — c'est même eux qui révèlent les fichiers empoisonnés.
    """
    reponse = await suivant(requete)
    if requete.url.path == "/predict":
        with etat.verrou:
            etat.appels += 1
            if reponse.status_code >= 400:
                etat.erreurs += 1
    return reponse


# --------------------------------------------------------------------------
# Schémas Pydantic — c'est ici que la pluviométrie négative est refusée
# --------------------------------------------------------------------------
class DemandePrediction(BaseModel):
    """Une ligne de relevé. Les champs inconnus (dont hg/ha_yield, le
    rendement réel présent dans les CSV de simulation) sont ignorés."""

    model_config = ConfigDict(extra="ignore")

    Area: str = Field(min_length=1, max_length=100, description="Pays")
    Item: str = Field(min_length=1, max_length=100, description="Culture")
    Year: int = Field(ge=1900, le=2100)
    # ge=0 : une pluviométrie négative est physiquement impossible. C'est
    # cette borne qui renvoie 422 sur les fichiers empoisonnés, déclenchant
    # les 5 tentatives du worker puis la file inference-requests-poison.
    average_rain_fall_mm_per_year: float = Field(ge=0, le=20000)
    pesticides_tonnes: float = Field(ge=0, le=10_000_000)
    avg_temp: float = Field(ge=-50, le=60)


class ReponsePrediction(BaseModel):
    # protected_namespaces=() : sans cela Pydantic refuse un champ préfixé
    # « model_ ». Or le contrat de l'énoncé impose le nom model_version.
    model_config = ConfigDict(protected_namespaces=())

    predicted_yield_hg_ha: float
    model_version: str
    inference_ms: float


# --------------------------------------------------------------------------
# Points de terminaison
# --------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    pret = etat.modele is not None
    return {
        "status": "ok" if pret else "degraded",
        "model_loaded": pret,
        "model_load_ms": etat.chargement_ms,
        "model_version": MODEL_VERSION,
        "error": etat.erreur_chargement,
    }


@app.get("/version")
def version() -> dict:
    return {"api_version": API_VERSION, "model_version": MODEL_VERSION, "commit": GIT_SHA}


@app.get("/metrics")
def metrics() -> dict:
    with etat.verrou:
        appels, preds, errs = etat.appels, etat.predictions, etat.erreurs
        total = etat.latence_totale_ms
    return {
        "total_calls": appels,
        "predictions": preds,
        "errors": errs,
        "avg_latency_ms": round(total / preds, 2) if preds else None,
        "model_version": MODEL_VERSION,
        # Compteurs en mémoire, donc propres à ce réplica. Avec
        # min-replicas 0 et max-replicas 2, ils repartent de zéro à chaque
        # démarrage à froid : la vue consolidée est dans Application Insights.
        "scope": "replica",
    }


@app.post("/predict", response_model=ReponsePrediction)
def predict(demande: DemandePrediction) -> ReponsePrediction:
    # Le comptage des appels et des erreurs est fait par le middleware.
    if etat.modele is None:
        raise HTTPException(status_code=503,
                            detail=f"Modèle non chargé: {etat.erreur_chargement}")

    ligne = pd.DataFrame([demande.model_dump()])[FEATURES]
    t0 = time.perf_counter()
    try:
        valeur = float(etat.modele.predict(ligne)[0])
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Échec de l'inférence: {type(e).__name__}") from e
    latence = (time.perf_counter() - t0) * 1000

    with etat.verrou:
        etat.predictions += 1
        etat.latence_totale_ms += latence

    if _compteur_inferences is not None:
        _compteur_inferences.add(1, {"item": demande.Item, "model_version": MODEL_VERSION})
    if _histogramme_latence is not None:
        _histogramme_latence.record(latence, {"model_version": MODEL_VERSION})

    return ReponsePrediction(
        predicted_yield_hg_ha=round(valeur, 2),
        model_version=MODEL_VERSION,
        inference_ms=round(latence, 2),
    )
