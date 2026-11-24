# web

Tableau de bord statique, hébergé dans le conteneur `$web` du compte de stockage
(section 4.4 de l'énoncé). Static Web Apps est souvent hors des régions autorisées pour un
compte Azure for Students, d'où ce choix.

Page HTML/JS avec Chart.js, actualisée toutes les 30 s depuis `GET /api/recent` :

- un tableau des dernières inférences ;
- au moins un graphique — ici le **rendement prédit contre le rendement réel** et le rendement
  moyen par culture.

Terminé quand un fichier nouvellement déposé apparaît dans le tableau de bord sans aucune
action manuelle.
