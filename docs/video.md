# Plan de tournage — livrable L5

**5 minutes maximum.** L'énoncé exige de montrer : la CI/CD en train de déployer, le dépôt d'un
fichier valide puis d'un fichier invalide, le tableau de bord mis à jour, Application Insights et
l'alerte.

Tourner en **1920 × 1080**, zoom du navigateur à **125 %** — un correcteur qui regarde sur un
portable doit pouvoir lire les URL et les codes HTTP.

## Ce qui est filmable aujourd'hui

| # | Durée | Plan | Prêt |
|---|---|---|---|
| 1 | 0:00–0:25 | Le dépôt GitHub : arborescence, README, 10 commits | oui |
| 2 | 0:25–0:55 | **La porte d'approbation** : onglet Actions, `Deploy` en *Waiting*, un coéquipier clique *Approve and deploy* | oui |
| 3 | 0:55–1:25 | Le déploiement se poursuit : OIDC, `az containerapp update`, vérification de `GET /version` | oui |
| 4 | 1:25–1:50 | `curl` sur l'API publique : `/health`, `/version` avec le commit, `/predict` | oui |
| 5 | 1:50–2:05 | Pluviométrie négative → **422** | oui |
| 6 | 2:05–2:20 | Portail Azure : réplicas de `api-cropyield` revenus à **0** | oui |
| 7 | 2:20–2:50 | Dépôt d'un fichier valide dans `input/`, résultat dans `output/` en moins d'une minute | §4.3 |
| 8 | 2:50–3:10 | Dépôt d'un fichier invalide → `rejected/` avec le motif | §4.3 |
| 9 | 3:10–3:30 | Fichier empoisonné → 5 tentatives → file `inference-requests-poison` | §4.3 |
| 10 | 3:30–4:00 | Tableau de bord : la nouvelle inférence apparaît sans action manuelle | §4.4 |
| 11 | 4:00–4:30 | Application Insights : les 3 requêtes KQL | §4.5 |
| 12 | 4:30–4:50 | L'alerte déclenchée, et l'e-mail reçu | §4.5 |
| 13 | 4:50–5:00 | Cost Management filtré sur `projet=dscc` : le coût réel | §4.7 |

Les plans 1 à 6 sont tournables maintenant. Les suivants attendent les sections correspondantes.

## Le plan 2, celui qui vaut le plus

C'est la preuve visuelle du « déploiement avec approbation manuelle » du barème. Deux choses à
cadrer explicitement :

- l'écran **Waiting** avec le nom de l'environnement `production` et la liste des relecteurs ;
- le fait que **l'approbateur n'est pas l'auteur du commit**. `prevent_self_review` est actif :
  l'autrice du commit ne *peut pas* s'approuver elle-même, l'API le confirme
  (`current_user_can_approve: false`). Filmer un coéquipier qui approuve rend la règle tangible.

Enchaîner immédiatement sur le plan 3 : le job reprend, et l'étape de vérification montre que
`GET /version` renvoie bien le SHA du commit qu'on vient d'approuver.

## Commandes à préparer dans un terminal, prêtes à coller

```bash
API=https://api-cropyield.calmmoss-a33fdd9d.francecentral.azurecontainerapps.io

curl -s $API/health | jq
curl -s $API/version | jq          # le champ commit doit valoir le SHA approuvé

curl -s -X POST $API/predict -H 'Content-Type: application/json' \
  -d '{"Area":"France","Item":"Potatoes","Year":2012,
       "average_rain_fall_mm_per_year":867,"pesticides_tonnes":72000,"avg_temp":11.2}' | jq

# Le rejet qui alimente la file poison
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/predict \
  -H 'Content-Type: application/json' \
  -d '{"Area":"France","Item":"Potatoes","Year":2012,
       "average_rain_fall_mm_per_year":-500,"pesticides_tonnes":72000,"avg_temp":11.2}'
```

Pour le plan 6, le nombre de réplicas :

```bash
az containerapp revision list -n api-cropyield -g rg-projet-cropyield \
  --query "[?properties.active].{revision:name, replicas:properties.replicas}" -o table
```

## Pièges de tournage

**Le démarrage à froid.** À 0 réplica, la première requête attend environ **10 secondes** : le
modèle met 9,1 s à se charger sur 0,25 vCPU. Ne coupe pas, ne t'affole pas — commente-le, c'est
précisément la preuve que l'application était bien descendue à zéro. C'est un atout, pas un défaut.

**L'ordre des plans 4 et 6 est contraignant.** Pour filmer les réplicas à 0, il faut ne plus
toucher à l'API pendant plusieurs minutes. Filme donc les `curl` (plan 4-5), puis va tourner
autre chose, et reviens sur le portail Azure pour le plan 6.

**Ne montre jamais** la chaîne de connexion Application Insights, les clés du compte de stockage,
ni la page des secrets GitHub. Une image qui dévoile un secret, même flouté ensuite, coûte
−2 points au barème.

**Les 5 minutes sont un maximum, pas un objectif.** Mieux vaut 4 minutes nettes que 5 minutes
bavardes. Écris le commentaire à l'avance plutôt que d'improviser.

## Répartition

L'énoncé demande que chaque membre présente sa partie. La vidéo est l'occasion de faire parler
les cinq voix : une personne par bloc de plans, annoncée à l'image.
