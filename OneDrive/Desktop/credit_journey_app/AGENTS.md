# Instructions pour les agents — CreditFlow

## Lire avant de modifier

1. Lire `HANDOFF.md` pour le contexte, les dernières modifications et la validation disponible.
2. Lire les parties utiles de `README.md` et, pour les comptes, les données ou le déploiement, `SECURITY.md`.
3. Inspecter le code concerné et l’état local : la note de passation est un instantané, le code reste la référence.

## Contraintes explicites de l’utilisateur

- **Ne pas utiliser Node.js**, npm, pnpm, yarn ou un outil de construction nécessitant Node. Ne pas convertir ce projet en React, Next.js ou une autre application Node.
- Utiliser Python, HTML, CSS et JavaScript navigateur natif. Le graphe actuel utilise DOM, SVG et Pointer Events, sans bibliothèque externe.
- L’interface et les messages destinés aux utilisateurs sont **en français**. Conserver les accents et le vocabulaire existant.
- Seuls les administrateurs modifient le parcours, les équipes, les sous-équipes, les effectifs, les macro-étapes et les comptes. Les lecteurs restent en lecture seule.
- La création des connexions se fait **par glisser-déposer entre étapes**, sans formulaire de sélection départ/arrivée. Garder aussi l’alternative clavier existante.
- Conserver le zoom des macro-étapes vers leurs sous-étapes, le retour à la vue d’ensemble et la vue « Toutes les sous-étapes ».
- Les sous-étapes reprennent le format des cartes macro, avec un style distinct : fond lavande, bordure latérale violette, badge « SOUS-ÉTAPE », titre, description et pied de carte.

## Conventions à préserver

- Garder un seul script classique autonome `static/app.js` pour l’espace de travail. Aucun import navigateur distant ni retour à Cytoscape sur CDN.
- Rendre les données utilisateur avec `textContent` et les API DOM ; pas de `innerHTML`, script inline ou évaluation dynamique.
- Appliquer les permissions **dans l’API**. Masquer un bouton dans l’interface ne constitue pas une autorisation.
- Conserver le middleware de session, les protections CSRF/origine, la validation stricte, les limites et les en-têtes de sécurité.
- Préserver le formulaire natif POST `/logout` : la déconnexion doit fonctionner même si JavaScript échoue.
- Préserver les champs d’origine en base. `display_name` et `display_description` traduisent les données de démonstration à l’affichage.
- Ne pas réinitialiser les données, resemer les exemples à chaque démarrage, changer les mots de passe ou créer un compte de test dans la base utilisateur.
- Les effectifs d’exemple restent signalés comme fictifs. Le total d’une équipe est calculé depuis ses sous-équipes ; ce n’est pas un effectif unique entre équipes.
- Toute nouvelle migration doit être compatible avec une base existante, idempotente et sauvegardée avant application à la base utilisateur.

## Graphe et UI

- Les coordonnées persistées sont celles du diagramme, avant pan/zoom. Ne pas remplacer les positions de l’utilisateur pour une simple retouche visuelle.
- Les dimensions des cartes doivent correspondre entre CSS et JavaScript : sous-étapes **270 × 180**, macros **280 × 180** à la date de passation.
- Si une dimension change, vérifier `stageScreenBox`, `boundaryPoint`, `connectionGeometry`, `fitGraph` et le placement des poignées de connexion.
- En vue détaillée, afficher seulement les étapes du groupe et les connexions dont les deux extrémités sont visibles. La vue globale détaillée conserve les liaisons entre groupes.
- Conserver les annulations de gestes, les échecs de sauvegarde avec restauration et la préférence `prefers-reduced-motion`.

## Données et environnement

- Dossier actuel : `C:\Users\anass\OneDrive\Desktop\credit_journey_app` ; shell PowerShell.
- Adresse locale par défaut : `http://127.0.0.1:5001`. Waitress écoute uniquement sur loopback. Respecter la variable `PORT` si définie.
- Le runtime privé `.runtime/python.exe` et l’environnement de développement `.venv` sont locaux et ignorés par Git. Ne pas les considérer comme livrés dans un checkout neuf.
- `journey.db` contient les données réelles de cet espace, les comptes et des secrets. Ne jamais l’afficher, le publier, le committer ou le servir comme fichier statique.
- Les tests utilisent des bases temporaires. Attention : **importer `app.py` exécute `init_db()`** ; définir `CREDIT_JOURNEY_DB` vers une base temporaire avant un import expérimental.
- Pour une sauvegarde cohérente, utiliser l’API SQLite `backup()`, avec destination hors de l’arborescence servie et hors de OneDrive ; emplacement local existant : `%LOCALAPPDATA%\CreditFlow\Backups`.
- Avant de redémarrer un serveur existant, vérifier son chemin, son dossier et sa configuration. Ne pas arrêter des processus Python sans rapport avec ce projet.
- Vérifier la racine Git avant toute opération : dans cet environnement, le dépôt détecté était au-dessus du dossier du projet. Ne pas utiliser `git add .` depuis une racine supérieure.
- Sous ce PowerShell, les scripts Python contenant des accents transmis par pipe ont déjà produit des `?`. Préférer des modifications UTF-8 directes ou un fichier Python enregistré en UTF-8 ; les exemples de commandes pipées de la passation ne contiennent que de l’ASCII.

## Validation et livraison

- Exécuter les vérifications adaptées au changement ; commandes dans `HANDOFF.md`. Les modifications de dimensions ou de structure des cartes nécessitent les tests du graphe et de la hiérarchie.
- Les tests MiniRacer exécutent le JavaScript via Python avec un DOM simulé. Ils ne prouvent pas le rendu réel d’un navigateur.
- Ne pas annoncer un contrôle visuel ou une validation navigateur non exécutés. Le navigateur automatisé était indisponible lors de la passation.
- Ne jamais garantir l’absence de toutes les vulnérabilités ou de zero-days. Le rapport de sécurité est daté et ses résultats ne constituent pas un audit permanent.
- Résumer en français ce qui a changé, les contrôles réellement exécutés et les limites utiles. Les changements de JS/CSS sont disponibles après rechargement, généralement **Ctrl+F5**.
