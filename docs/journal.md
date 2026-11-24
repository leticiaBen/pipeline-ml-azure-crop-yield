# Journal de temps — livrable L4

Une ligne par séance de travail. Les durées sont à ajuster par chaque membre.

| Date | Membre | Tâche | Durée | Blocage |
|---|---|---|---|---|
| 24/11/2026 | leticiaBen | Création du dépôt GitHub et de l'arborescence (`model/`, `api/`, `functions/`, `web/`, `infra/`, `docs/`, workflows) | 1h00 | — |
| 24/11/2026 | leticiaBen | Choix de la région Azure : relevé des régions autorisées, croisement avec Flex Consumption, Container Apps et Cosmos DB, comparaison des tarifs sur l'API publique des prix | 0h30 | `denmarkeast` autorisée mais sans Flex Consumption : 1 région sur 5 éliminée d'office |
| 24/11/2026 | leticiaBen | Déploiement du socle Azure : groupe étiqueté, Cosmos DB Free Tier, stockage et conteneurs, Log Analytics plafonné, Application Insights, environnement Container Apps, identité managée OIDC, budget 25 $ | 0h45 | Environnement Container Apps : 8 min de provisionnement. Sujet fédéré corrompu par zsh (voir décisions) |
| 24/11/2026 | leticiaBen | Attribution du rôle Contributor à l'identité GitHub, limité au groupe de ressources ; vérification du moindre privilège | 0h10 | — |
| 24/11/2026 | leticiaBen | Enregistrement des 3 identifiants Azure comme secrets d'environnement `production` ; scan de sécurité de l'arbre de travail | 0h10 | — |
| 24/11/2026 | leticiaBen | Changement de sujet : passage de la classification de commentaires YouTube à la prédiction du rendement agricole. Lecture de l'énoncé, recadrage du dépôt, passage en public, renommage, environnement `production`, correction du `.gitignore`, réécriture des README | 0h45 | `.gitignore` ignorait `*.joblib`, ce qui empêchait de commiter le modèle versionné attendu par le livrable L1 |

## Total par membre

| Membre | Total |
|---|---|
| leticiaBen | 3h20 |
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

## Prochaines étapes

- Section 4.1 : `model/train.py`, métriques contre la référence naïve, export `model-1.0.0.joblib`.
- Section 4.2 : API FastAPI, tests pytest, Dockerfile multi-étapes.
- Section 4.6 : `ci.yml` (ruff + pytest + publication GHCR), à mettre en place tôt.
- Répartir les parties entre les 5 membres et confirmer l'effectif auprès de l'enseignante.
