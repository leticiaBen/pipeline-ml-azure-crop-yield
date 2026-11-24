"""
Génère les fichiers CSV de simulation déposés dans le conteneur input/.

Trois familles, qui exercent les trois chemins du pipeline (section 4.3) :
  valid/    passe le dispatcher et l'API   -> output/ + Cosmos DB
  invalid/  rejeté par le dispatcher       -> rejected/
  poison/   passe le dispatcher, refusé par l'API en 422
            -> 5 tentatives -> file inference-requests-poison

Usage :
  python make_samples.py              # 12 lots valides, suffisant pour la démo
  python make_samples.py --lots 100   # pour le test de charge en bonus
"""

import argparse
import os

import pandas as pd

COLS = ["Area", "Item", "Year", "average_rain_fall_mm_per_year",
        "pesticides_tonnes", "avg_temp", "hg/ha_yield"]
TAILLE_LOT = 25
SORTIE = os.path.join("..", "samples")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", type=int, default=12,
                    help="nombre de lots valides à générer (défaut 12)")
    args = ap.parse_args()

    test = pd.read_csv("test.csv")[COLS]
    for d in ("valid", "invalid", "poison"):
        os.makedirs(os.path.join(SORTIE, d), exist_ok=True)

    # --- Lots valides -------------------------------------------------------
    # La colonne hg/ha_yield (le rendement réel) est conservée : l'API
    # l'ignore, mais le worker peut la stocker, ce qui permet au tableau de
    # bord de tracer la courbe « prédit contre réel » demandée en 4.4.
    # Les lots sont prélevés à intervalle régulier dans le jeu de test plutôt
    # qu'au début, pour couvrir plusieurs pays et plusieurs cultures.
    n = min(args.lots, len(test) // TAILLE_LOT)
    pas = len(test) // n
    for i in range(n):
        debut = i * pas
        lot = test.iloc[debut:debut + TAILLE_LOT]
        lot.to_csv(os.path.join(SORTIE, "valid", f"batch_{i + 1:03d}.csv"),
                   index=False)

    # --- Fichiers invalides : rejetés par le dispatcher ---------------------
    # 1. Colonne manquante -> échec de la validation de schéma
    test.iloc[:10].drop(columns=["avg_temp"]).to_csv(
        os.path.join(SORTIE, "invalid", "colonne_manquante.csv"), index=False)

    # 2. Mauvaise extension -> rejeté avant même la lecture du contenu
    with open(os.path.join(SORTIE, "invalid", "mauvaise_extension.txt"), "w") as f:
        f.write("Ce fichier n'est pas un CSV et doit atterrir dans rejected/.\n")

    # 3. Fichier vide -> cas limite classique, souvent oublié
    open(os.path.join(SORTIE, "invalid", "fichier_vide.csv"), "w").close()

    # --- Fichier empoisonné : valide pour le dispatcher, refusé par l'API ---
    # Une pluviométrie négative est structurellement valide (nombre dans la
    # bonne colonne) mais physiquement impossible : c'est la validation
    # Pydantic de l'API qui doit la refuser en 422. Le worker réessaie
    # 5 fois, puis le message part dans la file -poison.
    poison = test.iloc[:5].copy()
    poison["average_rain_fall_mm_per_year"] = -500
    poison.to_csv(os.path.join(SORTIE, "poison", "pluie_negative.csv"),
                  index=False)

    for d in ("valid", "invalid", "poison"):
        chemin = os.path.join(SORTIE, d)
        print(f"{d:<9} {len(os.listdir(chemin)):>3} fichier(s)")


if __name__ == "__main__":
    main()
