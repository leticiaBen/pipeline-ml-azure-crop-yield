"""Fixtures partagées. Le modèle est pris dans model/ du dépôt : les tests
vérifient le vrai modèle versionné, pas une imitation."""

import os
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[2]
MODELE = RACINE / "model" / "model-1.0.0.joblib"

# Doit être posé AVANT l'import de main, qui lit la variable au chargement.
os.environ.setdefault("MODEL_PATH", str(MODELE))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from main import app

    # Le gestionnaire de contexte déclenche le lifespan, donc le
    # chargement du modèle. Sans lui, /predict répondrait 503.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ligne_valide() -> dict:
    return {
        "Area": "France",
        "Item": "Potatoes",
        "Year": 2012,
        "average_rain_fall_mm_per_year": 867.0,
        "pesticides_tonnes": 72000.0,
        "avg_temp": 11.2,
    }
