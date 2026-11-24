# infra

Script `az` commenté créant le socle dans l'abonnement d'intégration (livrable L1).

Ordre imposé par les contraintes Azure for Students :

1. Vérifier les **régions autorisées** de l'abonnement et celles où Flex Consumption existe ;
   la région retenue doit figurer dans les deux listes (section 3.2 de l'énoncé).
2. Créer **Cosmos DB en premier**, en ligne de commande : c'est le service le plus souvent
   refusé pour manque de capacité, il valide donc la région au plus tôt.
3. Créer la **supervision** (espace Log Analytics plafonné à 0,2 Go/jour + Application Insights)
   avant le reste, sinon la CLI crée son propre espace sans plafond, éventuellement hors du
   groupe de ressources.
4. Container Apps (un seul environnement), puis la Function App.
5. Les **attributions de rôles** sont créées une seule fois par le propriétaire de l'abonnement :
   l'identité GitHub, simple Contributor sur le groupe, ne peut pas en créer.
6. L'abonnement **Event Grid** ne peut être créé qu'**après** le premier déploiement du code
   Functions (validation du point de terminaison).

Étiquettes obligatoires sur le groupe de ressources : `projet=dscc`, `equipe=<nom>`.
