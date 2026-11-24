"""
Expérience justifiant la décision « cible en logarithme » du README (section 3).

Entraîne deux fois le même modèle, à la seule différence de la transformation
de la cible, et compare :
  - l'erreur GLOBALE, en hg/ha (RMSE et MAE)
  - l'erreur RELATIVE par culture (MAPE), qui révèle l'effet réel

À lancer depuis le dossier model/ :
    python compare_cible.py
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from train import CAT, FEATURES, SEED, TARGET, TRAIN_MAX_YEAR, charger_donnees


def pipeline() -> Pipeline:
    return Pipeline([
        ("pre", ColumnTransformer(
            [("cat", OrdinalEncoder(handle_unknown="use_encoded_value",
                                    unknown_value=np.nan), CAT)],
            remainder="passthrough")),
        ("m", HistGradientBoostingRegressor(categorical_features=[0, 1],
                                            random_state=SEED)),
    ])


def main() -> None:
    df = charger_donnees()
    train = df[df["Year"] <= TRAIN_MAX_YEAR]
    test = df[df["Year"] > TRAIN_MAX_YEAR]

    modeles = {
        "sans log": pipeline(),
        "avec log": TransformedTargetRegressor(
            regressor=pipeline(), func=np.log1p, inverse_func=np.expm1),
    }

    pred = {}
    print()
    for nom, mdl in modeles.items():
        mdl.fit(train[FEATURES], train[TARGET])
        # Un modèle sans transformation peut prédire des valeurs négatives,
        # dépourvues de sens pour un rendement : on les ramène à 1.
        pred[nom] = np.clip(mdl.predict(test[FEATURES]), 1, None)
        print(f"{nom:<10} RMSE global {np.sqrt(mean_squared_error(test[TARGET], pred[nom])):>8.0f}"
              f"   MAE global {mean_absolute_error(test[TARGET], pred[nom]):>8.0f}")

    print()
    print("Erreur relative moyenne par culture (MAPE)")
    print(f"{'culture':<22}{'rendement moyen':>17}{'sans log':>11}{'avec log':>11}{'écart':>9}")
    print("-" * 70)

    lignes = []
    for item in test["Item"].unique():
        masque = (test["Item"] == item).to_numpy()
        y = test.loc[masque, TARGET].to_numpy()
        sans = np.mean(np.abs(pred["sans log"][masque] - y) / y) * 100
        avec = np.mean(np.abs(pred["avec log"][masque] - y) / y) * 100
        lignes.append((y.mean(), item, sans, avec))

    for moyenne, item, sans, avec in sorted(lignes):
        print(f"{item:<22}{moyenne:>17.0f}{sans:>10.1f}%{avec:>10.1f}%{avec - sans:>+8.1f}")

    print()
    print("Lecture : le logarithme dégrade l'erreur globale en hg/ha, dominée par")
    print("les cultures à fort rendement, mais améliore l'erreur relative sur la")
    print("majorité des cultures. Décision retenue : garder le logarithme.")


if __name__ == "__main__":
    main()
