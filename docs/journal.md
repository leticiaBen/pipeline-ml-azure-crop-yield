# Journal de temps — livrable L4

Une ligne par séance de travail. Les durées sont à ajuster par chaque membre.

| Date | Membre | Tâche | Durée | Blocage |
|---|---|---|---|---|
| 24/11/2026 | leticiaBen | Création du dépôt GitHub et de l'arborescence (`model/`, `api/`, `functions/`, `web/`, `infra/`, `docs/`, workflows) | 1h00 | — |
| 24/11/2026 | leticiaBen | Choix de la région Azure : relevé des régions autorisées, croisement avec Flex Consumption, Container Apps et Cosmos DB, comparaison des tarifs sur l'API publique des prix | 0h30 | `denmarkeast` autorisée mais sans Flex Consumption : 1 région sur 5 éliminée d'office |
| 24/11/2026 | leticiaBen | Déploiement du socle Azure : groupe étiqueté, Cosmos DB Free Tier, stockage et conteneurs, Log Analytics plafonné, Application Insights, environnement Container Apps, identité managée OIDC, budget 25 $ | 0h45 | Environnement Container Apps : 8 min de provisionnement. Sujet fédéré corrompu par zsh (voir décisions) |
| 24/11/2026 | leticiaBen | Attribution du rôle Contributor à l'identité GitHub, limité au groupe de ressources ; vérification du moindre privilège | 0h10 | — |
| 24/11/2026 | leticiaBen | Enregistrement des 3 identifiants Azure comme secrets d'environnement `production` ; scan de sécurité de l'arbre de travail | 0h10 | — |
| 24/11/2026 | leticiaBen | Section 4.1 : environnement Python 3.12, `train.py`, entraînement, évaluation contre la référence naïve, export du modèle 1.0.0, `requirements.txt` figé, lots de simulation | 1h15 | `metrics.json` annonçait Python 3.13.7 au lieu de 3.12.7 : `os.popen("python3 --version")` interrogeait le Python du système et non celui de l'environnement virtuel |
| 24/11/2026 | leticiaBen | Comparaison chiffrée cible brute contre cible en logarithme, par culture ; décision et documentation | 0h20 | — |
| 24/11/2026 | leticiaBen | Section 4.2 : API FastAPI (4 endpoints, validation Pydantic), 12 tests pytest, configuration ruff | 1h30 | — |
| 24/11/2026 | leticiaBen | Dockerfile multi-étapes, construction et réduction de l'image, tests du conteneur de bout en bout | 1h20 | Image initiale à 816 Mo contre une limite de 500 Mo ; `docker images` annonce une taille trompeuse |
| 24/11/2026 | leticiaBen | Changement de sujet : passage de la classification de commentaires YouTube à la prédiction du rendement agricole. Lecture de l'énoncé, recadrage du dépôt, passage en public, renommage, environnement `production`, correction du `.gitignore`, réécriture des README | 0h45 | `.gitignore` ignorait `*.joblib`, ce qui empêchait de commiter le modèle versionné attendu par le livrable L1 |

## Total par membre

| Membre | Total |
|---|---|
| leticiaBen | 7h45 |
| NourMontacer01 | — |
| Essid01 | — |
| Yacine-BJ | — |
| hibabouchaala | — |

## Décisions

**24/11/2026 — Jeu de données.** Abandon de la classification de commentaires YouTube au profit
du *Crop Yield Prediction Dataset* (Kaggle, `patelris`, données FAO et Banque mondiale). Tâche de
régression : prédire le rendement en hg/ha. Jeu de données ouvert, ≈ 2 Mo, bien sous la limite de
50 Mo de l'énoncé.

**24/11/2026 — Découpage temporel plutôt qu'aléatoire.** Entraînement sur 1990–2009, test sur
2010–2013. Un découpage aléatoire mélangerait les années et laisserait le modèle « voir le
futur » : les scores seraient flatteurs mais malhonnêtes. Argument à défendre en soutenance.

**24/11/2026 — Modèle.** `HistGradientBoostingRegressor` plutôt qu'une Random Forest : une forêt
sur ce jeu de données dépasse facilement 100 Mo, ce que l'énoncé interdit. Cible entraînée en
logarithme, les rendements variant d'un facteur 10 selon la culture.

**24/11/2026 — Dépôt public.** Le dépôt était privé. Les relecteurs obligatoires d'un
environnement GitHub ne sont pas disponibles sur les offres Free, Pro et Team pour un dépôt privé,
ce qui rendait impossible le sujet fédéré OIDC `environment:production` de la section 6. Dépôt
passé en public et renommé `pipeline-ml-azure-crop-yield`. Historique vérifié : aucun secret.

**24/11/2026 — Environnement `production` protégé.** Les cinq membres sont relecteurs
obligatoires, l'auto-approbation est interdite et le contournement administrateur est désactivé.
Un déploiement vers Azure exige donc l'approbation d'un membre autre que l'auteur du commit.
Première tentative échouée et instructive : GitHub avait renvoyé un `200 OK` avec une liste de
relecteurs **vide**, parce que les invitations n'étaient pas encore acceptées (permission `read`
au lieu de `write`). Une porte d'approbation sans relecteur aurait bloqué tout déploiement.

**24/11/2026 — À vérifier auprès de l'enseignante.** L'énoncé prévoit des équipes de 3
(recommandé) ou 4 étudiants ; nous sommes 5. Confirmer que c'est accepté et noter la réponse ici.

**24/11/2026 — Région retenue : `francecentral`.** Sur les 5 régions autorisées par la politique
de l'abonnement, `denmarkeast` ne propose pas Flex Consumption et a été éliminée. Les 4 autres
passaient les trois tests. `francecentral` a été retenue parce qu'elle est la moins chère sur les
deux seuls postes facturables du projet (stockage 0,0172 €/Go/mois, ingestion de logs
0,5611 €/Go), la plus mature donc la moins susceptible de refuser pour capacité, et surtout parce
que l'abonnement y héberge déjà trois groupes de ressources fonctionnels — une preuve concrète
plutôt qu'un pari. Justification détaillée dans la section 2 du README.

**24/11/2026 — Piège zsh sur le sujet fédéré OIDC, à retenir.** La commande
`--subject "repo:$REPO:environment:production"` a produit `repo:nvironment:production`. Sous zsh,
`$REPO:e` est interprété comme le modificateur d'historique « extension du nom de fichier », qui
est vide ici, et le `e` de `environment` est consommé au passage. Les accolades `${REPO}` sont
obligatoires. Détecté en relisant la sortie de la commande ; non détecté, il aurait produit un
`AADSTS700213` au premier déploiement, erreur que l'énoncé signale sans en donner cette cause.

**24/11/2026 — Ordre de création respecté.** Cosmos DB avant tout le reste (service le plus
souvent refusé pour capacité : il valide la région au plus tôt — abouti en 1 min 37), puis la
supervision avant Container Apps, pour éviter que la CLI ne crée son propre espace Log Analytics
sans plafond et hors du groupe de ressources.

**24/11/2026 — Moindre privilège de l'identité GitHub.** L'identité `id-github-cropyield` a
reçu le rôle **Contributor sur le seul groupe de ressources**, et rien d'autre : zéro attribution
au niveau de l'abonnement, et aucun rôle lui permettant d'attribuer des rôles (ni Owner, ni User
Access Administrator, ni RBAC Administrator). Vérifié par `az role assignment list --all`, qui
renvoie exactement une ligne. Conséquence assumée : les attributions de rôles de la Function App
devront être appliquées à la main par la propriétaire de l'abonnement, hors du pipeline CI/CD —
commandes préparées dans `infra/03-roles.sh`. `--assignee-object-id` est utilisé partout pour
éviter toute lecture de l'annuaire Entra ID, interdite aux comptes étudiants.

**24/11/2026 — Secrets portés par l'environnement, pas par le dépôt.** `AZURE_CLIENT_ID`,
`AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID` sont enregistrés comme secrets de l'environnement
`production` plutôt qu'à l'échelle du dépôt. Seul un job déclarant `environment: production` peut
donc les lire — ce qui est de toute façon obligatoire, le sujet fédéré OIDC l'exigeant. `ci.yml`
n'y a aucun accès. Le dépôt ne porte aucun secret global. Scan de l'arbre de travail effectué
(chaînes de connexion, clés de compte de stockage, SAS, clés privées, adresses e-mail) : aucune
correspondance, ce qui écarte la pénalité de −2 points.

**24/11/2026 — Modèle 1.0.0 entraîné, section 4.1 terminée.** HistGradientBoostingRegressor,
cible en logarithme, découpage temporel 1990-2009 / 2010-2013, graine 42.
RMSE 23 118 contre 61 468 pour la référence naïve, MAE 12 246 contre 36 357,
R² 0.9411 contre 0.5835 — soit 66 % d'erreur absolue en moins. Les deux
contraintes de l'énoncé sont tenues avec de larges marges : 0.531 Mo pour une limite de
100 Mo, et 28.2 ms d'inférence à froid pour une limite de 1 s.

**24/11/2026 — Version du jeu de données épinglée.** `train.py` demande
`patelris/crop-yield-prediction-dataset/versions/7` et non la dernière version. Avec « latest »,
une republication par l'auteur ferait varier les métriques du README sans qu'aucune ligne de code
n'ait changé. L'énoncé exige un script reproductible.

**24/11/2026 — Reproductibilité vérifiée, pas supposée.** Deux exécutions successives produisent
un `model-1.0.0.joblib` de même empreinte MD5 et des métriques identiques. Le temps d'inférence,
lui, varie d'une exécution à l'autre selon la charge de la machine (28.2 ms relevés après
une première mesure à 5,73 ms) : les deux restent deux ordres de grandeur sous la limite.

**24/11/2026 — Deux fragilités attendues qui ne se déclenchent pas sur ces données.** Vérification
faite : dans `yield_df.csv` la pluviométrie est déjà numérique (contrairement au `rainfall.csv`
source), et les 10 cultures du jeu de test sont toutes présentes dans l'entraînement. Les deux
garde-fous ont été conservés — conversion numérique explicite et repli de la référence naïve sur
la moyenne globale — car ils ne coûtent rien et protègent d'une évolution du jeu de données. En
revanche un cas réel existe : **le Soudan apparaît dans le test sans être dans l'entraînement**.
L'encodeur le traduit en NaN, que HistGradientBoosting traite nativement comme une valeur
manquante.

**24/11/2026 — Licence du jeu de données.** World Bank Dataset Terms of Use, relevée sur la fiche
Kaggle. Citée dans le README avec les sources d'origine FAO et Banque mondiale, comme l'exige la
section 4.1.

**24/11/2026 — Cible en logarithme : décision arbitrée, pas supposée.** Les deux variantes ont
été entraînées et comparées (`model/compare_cible.py`). Résultat contre-intuitif : **la cible
brute donne une meilleure erreur globale** (RMSE 20 102 contre 23 118). Mais l'erreur globale en
hg/ha est dominée par les cultures à fort rendement. En erreur relative par culture, le
logarithme gagne sur 8 cultures sur 10 — le sorgho passe de 39,3 % à 24,4 % — et les deux qui se
dégradent, ignames et pomme de terre, perdent moins d'un point. Décision : garder le logarithme,
un modèle exploitable sur les dix cultures valant mieux qu'un spécialiste des gros rendements.
Les deux variantes écrasent de toute façon la référence naïve, donc la section 4.1 est
satisfaite dans les deux cas. Tableau complet dans la section 3 du README.

**24/11/2026 — Image Docker : 816 Mo au premier essai, pour une limite de 500 Mo.** Mesures
avant d'agir : la couche du venv pesait 483 Mo, dont 205 Mo de bibliothèques natives, 100 Mo de
suites de tests et 13 Mo de pip. Quatre réductions appliquées dans l'étape de construction —
suppression des répertoires `tests`, `strip --strip-unneeded` sur les `.so`, `uvicorn` sans
l'extra `[standard]`, retrait de pip/setuptools/wheel, `pip install --no-compile`. Résultat :
387 Mo de système de fichiers, 411 Mo de couches, 112 Mo compressés.

**24/11/2026 — `docker images` donne une taille trompeuse, à savoir pour la soutenance.** La
commande affiche 522 Mo, ce qui ferait croire à un dépassement. Le magasin containerd de Docker
Desktop additionne les couches décompressées et les blobs compressés : 411 + 112 = 523. Vérifié
par une mesure indépendante, `du` à l'intérieur du conteneur, qui donne 387 Mo. Les trois chiffres
sont documentés dans le README pour couper court à l'objection.

**24/11/2026 — `/metrics` comptait mal les appels.** Première version : le compteur était
incrémenté dans la fonction `predict`, donc un rejet 422 n'apparaissait jamais, Pydantic validant
avant l'entrée dans la fonction. Or l'énoncé demande le nombre d'appels, et les 422 sont
précisément le trafic qui révèle les fichiers empoisonnés. Corrigé par un middleware HTTP qui
compte tous les appels à `/predict` et distingue les erreurs. Un test couvre le cas.

**24/11/2026 — Le chargement du modèle prend 1,5 s en conteneur, pas 11 ms.** Les 11 ms mesurés
par `train.py` correspondent à un processus déjà chaud et un fichier en cache. À froid dans le
conteneur, c'est 1 511 ms. D'où `--start-period=20s` sur le `HEALTHCHECK`, et c'est la valeur à
retenir pour la sonde readiness de Container Apps : une sonde trop impatiente redémarrerait le
conteneur en boucle. L'inférence, elle, reste à 82 ms au premier appel et 3,8 ms ensuite, très
loin de la limite d'une seconde.

**24/11/2026 — Limite assumée du découpage temporel, visible sur un vrai lot.** La pomme de terre
albanaise est sous-estimée de 31 à 34 % sur 2010 et 2011 : son rendement a fortement progressé
après 2009, et le modèle n'a appris que jusqu'à cette année-là. Un découpage aléatoire masquerait
ce défaut. C'est le prix de l'honnêteté de l'évaluation, et un bon sujet de question en soutenance.

## Prochaines étapes

- Section 4.6 : `ci.yml` (ruff + pytest + publication GHCR), à mettre en place tôt.
- Répartir les parties entre les 5 membres et confirmer l'effectif auprès de l'enseignante.
