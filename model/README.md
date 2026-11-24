# model

Entraînement et évaluation du modèle de prédiction du rendement agricole (section 4.1 de l'énoncé).

| Fichier | Rôle |
|---|---|
| `train.py` | Téléchargement du jeu de données, découpage temporel, entraînement, évaluation, export |
| `make_samples.py` | Génération des lots CSV de démonstration (valides, invalides, empoisonnés) |
| `requirements.txt` | Dépendances figées (`pip freeze`) |
| `model-1.0.0.joblib` | Modèle versionné — **livrable L1** |
| `metrics.json` | RMSE, MAE, R² du modèle et de la référence naïve |
| `test.csv` | Jeu de test 2010–2013, sert à générer les lots de simulation |

Exigences à respecter : graine aléatoire fixée, jeu de test séparé, au moins deux métriques
comparées à une référence naïve, modèle < 100 Mo, inférence < 1 s sur CPU.

Aucun calcul Azure n'est nécessaire : l'entraînement se fait en local.
