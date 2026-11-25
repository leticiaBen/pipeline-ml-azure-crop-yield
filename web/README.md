# web

Tableau de bord du pipeline — section 4.4 de l'énoncé.

Page statique unique, hébergée dans le conteneur `$web` du compte de stockage. Static Web Apps
est souvent hors des régions autorisées pour un compte Azure for Students, d'où ce choix.

**En ligne** : https://stcropyieldpipe.z28.web.core.windows.net/

## Contenu

| Élément | |
|---|---|
| 4 tuiles | lots traités, lignes prédites, écart moyen, version du modèle |
| Graphique 1 | prédit contre réel, par lot, du plus ancien au plus récent |
| Graphique 2 | rendement moyen par culture, agrégé sur tous les lots |
| Tableau | les 20 dernières inférences, écart coloré selon qu'il dépasse 10 % |

Actualisation automatique **toutes les 30 secondes**, et aussi au retour sur l'onglet — pour ne
pas lire des chiffres périmés après une pause.

## Source de données

Une seule : `GET /api/recent`, la fonction HTTP du dossier `functions/`. Le CORS est limité à
l'origine de ce site, posé à deux niveaux : dans le code de la fonction, et dans la configuration
CORS de la Function App.

> L'hôte Functions **intercepte les requêtes `OPTIONS`** et y répond depuis sa propre
> configuration CORS, sans jamais appeler la fonction. Les en-têtes posés dans le code ne
> suffisent donc pas pour un pré-vol : il faut aussi `az functionapp cors add`. Cela dit, un `GET`
> simple n'est pas pré-volé, et c'est tout ce que fait cette page.

## Déployer

```bash
az storage blob upload --account-name stcropyieldpipe -c '$web' -n index.html \
  -f web/index.html --content-type "text/html; charset=utf-8" --overwrite
```

## Deux pièges rencontrés, et vérifiés dans un navigateur

**L'empreinte SRI de Chart.js.** Écrite de mémoire, elle était fausse. Le navigateur refusait
alors le script, et la page s'affichait **sans aucun graphique** — tuiles et tableau intacts,
canevas vides, aucune erreur ailleurs que dans la console. L'empreinte est désormais calculée sur
le fichier réel :

```bash
curl -s https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js \
  | openssl dgst -sha512 -binary | openssl base64 -A
```

**L'attribut `hidden` et `display: flex`.** L'attribut HTML `hidden` ne pose `display: none` que
via la feuille de style du navigateur : une règle d'auteur comme `display: flex` l'emporte, et
l'élément reste visible. Le message « en attente d'un lot traité » s'affichait par-dessus un
graphique qui avait pourtant des données. Corrigé par `[hidden] { display: none !important; }`.

Les deux ne se voient qu'en ouvrant la page. Aucun test automatique ne les aurait révélés.
