"""
Entraînement du modèle de prédiction du rendement agricole.
Section 4.1 de l'énoncé — ECE Paris, Systèmes distribués et IA.

Produit, dans le dossier courant :
  - model-1.0.0.joblib  le modèle versionné (livrable L1)
  - metrics.json        RMSE, MAE et R² du modèle et de la référence naïve
  - test.csv            le jeu de test 2010-2013, base des lots de simulation

Reproductibilité : graine fixée, version du jeu de données épinglée,
versions des bibliothèques enregistrées dans metrics.json.
Aucun calcul Azure n'est nécessaire.
"""

import json
import os
import sys
import time

import joblib
import kagglehub
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

SEED = 42
MODEL_VERSION = "1.0.0"
TARGET = "hg/ha_yield"
CAT = ["Area", "Item"]
NUM = ["Year", "average_rain_fall_mm_per_year", "pesticides_tonnes", "avg_temp"]
FEATURES = CAT + NUM

TRAIN_MAX_YEAR = 2009          # entraînement 1990-2009
# Version épinglée : "latest" ferait silencieusement varier les métriques
# si l'auteur publiait une nouvelle version du jeu de données.
DATASET = "patelris/crop-yield-prediction-dataset/versions/7"


def charger_donnees() -> pd.DataFrame:
    """Télécharge le jeu de données et le nettoie."""
    chemin = kagglehub.dataset_download(DATASET)
    df = pd.read_csv(os.path.join(chemin, "yield_df.csv"))

    # La colonne d'index exportée par pandas ne porte aucune information.
    df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])

    # La fusion des températures en amont a dupliqué des lignes : 2310 sur
    # 28242. Sans cette ligne, les doublons se répartiraient entre
    # entraînement et test et gonfleraient les scores.
    avant = len(df)
    df = df.drop_duplicates()
    print(f"Doublons supprimés : {avant - len(df)} ({avant} -> {len(df)} lignes)")

    # Ceinture et bretelles : dans yield_df.csv ces colonnes sont déjà
    # numériques, mais les CSV sources de ce jeu de données contiennent des
    # valeurs textuelles. Si une version ultérieure en réintroduisait, mieux
    # vaut un NaN explicite — que HistGradientBoosting sait traiter — qu'une
    # colonne silencieusement convertie en chaînes.
    for c in NUM + [TARGET]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=[TARGET])

    return df


def construire_modele() -> TransformedTargetRegressor:
    """Pipeline complet : encodage des catégories puis gradient boosting."""
    pre = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value",
                                unknown_value=np.nan), CAT)],
        remainder="passthrough",
    )

    # HistGradientBoosting plutôt qu'une forêt aléatoire : une Random Forest
    # sur ces 26 000 lignes dépasse les 100 Mo que l'énoncé interdit.
    # Les catégories encodées occupent les positions 0 et 1 après le
    # ColumnTransformer. Area compte ~101 pays, sous la limite de 255
    # catégories de l'implémentation.
    hgb = HistGradientBoostingRegressor(categorical_features=[0, 1],
                                        random_state=SEED)

    # Cible en logarithme : les rendements vont de 16 992 hg/ha pour le soja
    # à 198 666 pour la pomme de terre, soit un facteur 12. Sans cette
    # transformation, l'erreur quadratique se concentrerait sur les cultures
    # à fort rendement et le modèle négligerait les autres.
    return TransformedTargetRegressor(
        regressor=Pipeline([("pre", pre), ("hgb", hgb)]),
        func=np.log1p,
        inverse_func=np.expm1,
    )


def scores(y_vrai, y_pred) -> dict:
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_vrai, y_pred))),
        "mae": float(mean_absolute_error(y_vrai, y_pred)),
        "r2": float(r2_score(y_vrai, y_pred)),
    }


def main() -> None:
    df = charger_donnees()

    # Découpage TEMPOREL et non aléatoire : un découpage aléatoire mélangerait
    # les années et laisserait le modèle apprendre sur 2013 pour prédire 2005.
    # Les scores seraient meilleurs, mais mensongers.
    train = df[df["Year"] <= TRAIN_MAX_YEAR]
    test = df[df["Year"] > TRAIN_MAX_YEAR]
    print(f"Entraînement 1990-{TRAIN_MAX_YEAR} : {len(train)} lignes")
    print(f"Test {TRAIN_MAX_YEAR + 1}-2013        : {len(test)} lignes")

    inconnus = sorted(set(test["Area"]) - set(train["Area"]))
    if inconnus:
        print(f"Pays présents dans le test mais absents de l'entraînement : "
              f"{inconnus} -> encodés en NaN, géré nativement par le modèle")

    modele = construire_modele()
    modele.fit(train[FEATURES], train[TARGET])

    # Référence naïve imposée par l'énoncé : le rendement moyen de la culture,
    # calculé sur le seul jeu d'entraînement. Le repli sur la moyenne globale
    # couvre le cas d'une culture absente de l'entraînement : sans lui,
    # r2_score lèverait une exception sur des NaN.
    moyennes = train.groupby("Item")[TARGET].mean()
    reference = test["Item"].map(moyennes).fillna(train[TARGET].mean())

    prediction = modele.predict(test[FEATURES])

    metriques = {
        "model_version": MODEL_VERSION,
        "dataset": DATASET,
        "split": {"train": "1990-2009", "test": "2010-2013",
                  "n_train": int(len(train)), "n_test": int(len(test))},
        "seed": SEED,
        "model": scores(test[TARGET], prediction),
        "baseline": scores(test[TARGET], reference),
    }

    # --- Preuves exigées par la section 4.1 : taille et temps d'inférence ---
    fichier = f"model-{MODEL_VERSION}.joblib"
    joblib.dump(modele, fichier)
    taille_mo = os.path.getsize(fichier) / 1e6

    une_ligne = test[FEATURES].head(1)
    t0 = time.perf_counter()
    modele.predict(une_ligne)
    froid_ms = (time.perf_counter() - t0) * 1000
    chaud = []
    for _ in range(100):
        t0 = time.perf_counter()
        modele.predict(une_ligne)
        chaud.append((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    joblib.load(fichier)
    chargement_ms = (time.perf_counter() - t0) * 1000

    metriques["contraintes"] = {
        "taille_mo": round(taille_mo, 3),
        "taille_limite_mo": 100,
        "inference_froide_ms": round(froid_ms, 2),
        "inference_mediane_ms": round(float(np.median(chaud)), 2),
        "inference_limite_ms": 1000,
        "chargement_modele_ms": round(chargement_ms, 2),
    }
    # sys.version et non `python3 --version` : ce dernier interroge le Python
    # du système, pas celui de l'environnement virtuel qui exécute le script.
    metriques["versions"] = {
        "python": sys.version.split()[0],
        "scikit_learn": __import__("sklearn").__version__,
        "pandas": pd.__version__,
        "joblib": joblib.__version__,
    }

    with open("metrics.json", "w") as f:
        json.dump(metriques, f, indent=2, ensure_ascii=False)
    test.to_csv("test.csv", index=False)

    # --- Rapport ---
    print()
    print(f"{'':<28}{'RMSE':>12}{'MAE':>12}{'R2':>9}")
    for nom, cle in (("Référence naïve (moy./culture)", "baseline"),
                     (f"Modèle {MODEL_VERSION}", "model")):
        s = metriques[cle]
        print(f"{nom:<28}{s['rmse']:>12.1f}{s['mae']:>12.1f}{s['r2']:>9.4f}")

    m, b = metriques["model"], metriques["baseline"]
    print()
    print(f"Gain sur le RMSE : {(1 - m['rmse'] / b['rmse']) * 100:.1f} %")
    print(f"Gain sur le MAE  : {(1 - m['mae'] / b['mae']) * 100:.1f} %")
    print()
    c = metriques["contraintes"]
    ok_t = "OK" if taille_mo < 100 else "DEPASSE"
    ok_i = "OK" if c["inference_froide_ms"] < 1000 else "DEPASSE"
    print(f"Taille du modèle   : {taille_mo:.3f} Mo   (< 100 Mo)  {ok_t}")
    print(f"Inférence à froid  : {froid_ms:.2f} ms   (< 1000 ms) {ok_i}")
    print(f"Inférence médiane  : {np.median(chaud):.2f} ms")
    print(f"Chargement         : {chargement_ms:.2f} ms")


if __name__ == "__main__":
    main()
