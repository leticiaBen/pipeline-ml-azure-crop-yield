"""
Tests de l'API d'inférence. L'énoncé (section 4.2) en exige au moins trois :
succès, entrée invalide (422), corps absent. Les suivants couvrent les trois
autres points de terminaison et le scénario du fichier empoisonné.
"""


# --------------------------------------------------------------------------
# Les trois tests exigés par l'énoncé
# --------------------------------------------------------------------------
def test_predict_succes(client, ligne_valide):
    r = client.post("/predict", json=ligne_valide)
    assert r.status_code == 200
    corps = r.json()
    assert corps["model_version"] == "1.0.0"
    assert corps["inference_ms"] > 0
    # Un rendement doit être strictement positif, et rester dans un ordre de
    # grandeur plausible : la pomme de terre tourne autour de 200 000 hg/ha.
    assert 0 < corps["predicted_yield_hg_ha"] < 1_000_000


def test_predict_entree_invalide_422(client, ligne_valide):
    """Pluviométrie négative : c'est ce cas qui, en production, provoque les
    5 tentatives du worker puis l'envoi dans la file -poison."""
    empoisonnee = ligne_valide | {"average_rain_fall_mm_per_year": -500}
    r = client.post("/predict", json=empoisonnee)
    assert r.status_code == 422
    champs = [".".join(str(x) for x in d["loc"]) for d in r.json()["detail"]]
    assert any("average_rain_fall_mm_per_year" in c for c in champs)


def test_predict_corps_absent(client):
    r = client.post("/predict")
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Les trois autres points de terminaison
# --------------------------------------------------------------------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    corps = r.json()
    assert corps["status"] == "ok"
    assert corps["model_loaded"] is True
    # Exigé par la section 4.2 : /health renvoie le temps de chargement.
    assert corps["model_load_ms"] is not None and corps["model_load_ms"] > 0


def test_version(client):
    r = client.get("/version")
    assert r.status_code == 200
    # Le champ commit permet de verifier qu'un deploiement a bien pris effet :
    # c'est le critere « visible via GET /version » de la section 4.6.
    assert set(r.json()) == {"api_version", "model_version", "commit"}
    assert r.json()["commit"]  # non vide, « inconnu » hors deploiement


def test_metrics_compte_les_appels(client, ligne_valide):
    avant = client.get("/metrics").json()["predictions"]
    client.post("/predict", json=ligne_valide)
    apres = client.get("/metrics").json()
    assert apres["predictions"] == avant + 1
    assert apres["avg_latency_ms"] > 0


# --------------------------------------------------------------------------
# Validation plus fine
# --------------------------------------------------------------------------
def test_champ_manquant_422(client, ligne_valide):
    del ligne_valide["avg_temp"]
    assert client.post("/predict", json=ligne_valide).status_code == 422


def test_type_invalide_422(client, ligne_valide):
    assert client.post("/predict",
                       json=ligne_valide | {"Year": "mille"}).status_code == 422


def test_temperature_absurde_422(client, ligne_valide):
    assert client.post("/predict",
                       json=ligne_valide | {"avg_temp": 300}).status_code == 422


def test_rendement_reel_ignore(client, ligne_valide):
    """Les CSV de simulation contiennent hg/ha_yield. L'API doit l'ignorer
    sans broncher, et surtout ne pas s'en servir pour prédire."""
    r = client.post("/predict", json=ligne_valide | {"hg/ha_yield": 999999})
    assert r.status_code == 200
    sans = client.post("/predict", json=ligne_valide).json()
    assert r.json()["predicted_yield_hg_ha"] == sans["predicted_yield_hg_ha"]


def test_pays_inconnu_ne_plante_pas(client, ligne_valide):
    """Le Soudan est absent du jeu d'entraînement : l'encodeur le traduit en
    NaN, que le modèle doit absorber sans lever d'exception."""
    r = client.post("/predict", json=ligne_valide | {"Area": "Wakanda"})
    assert r.status_code == 200
    assert r.json()["predicted_yield_hg_ha"] > 0


def test_metrics_compte_aussi_les_rejets(client, ligne_valide):
    """Un 422 est un appel réel : il doit apparaître dans /metrics, sinon le
    tableau de bord ne verrait jamais passer les fichiers empoisonnés."""
    avant = client.get("/metrics").json()
    client.post("/predict", json=ligne_valide | {"average_rain_fall_mm_per_year": -1})
    apres = client.get("/metrics").json()
    assert apres["total_calls"] == avant["total_calls"] + 1
    assert apres["errors"] == avant["errors"] + 1
    # Un rejet n'est pas une prédiction : la latence moyenne ne doit pas bouger.
    assert apres["predictions"] == avant["predictions"]
