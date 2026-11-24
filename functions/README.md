# functions

**Une seule** Function App Flex Consumption (Python 3.12, 512 Mo, modèle de programmation v2)
contenant les trois fonctions du pipeline (section 4.3 de l'énoncé).

| Fonction | Déclencheur | Rôle |
|---|---|---|
| `dispatcher` | Event Grid | Vérifie extension, taille et schéma du blob déposé dans `input/` ; publie un message JSON dans `inference-requests`, ou copie dans `rejected/` avec le motif |
| `worker` | Storage Queue | Appelle l'API, écrit le JSON dans `output/` et les métadonnées dans Cosmos DB ; **idempotent** (identifiant = nom du blob + ETag, écriture en upsert) |
| `recent` | HTTP | `GET /api/recent` : les 20 dernières inférences, CORS limité à l'origine du site |

Reprises : `maxDequeueCount = 5`, puis la file `inference-requests-poison` qui joue le rôle de DLQ.

Aucun secret dans le dépôt : paramètres d'application et connexions par identité managée.
`local.settings.json` est ignoré par Git.
