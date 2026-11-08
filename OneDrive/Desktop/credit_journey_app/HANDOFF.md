# Passation à un autre modèle — CreditFlow

Dernière mise à jour : **8 novembre 2026**. Lire aussi `AGENTS.md` avant de travailler.

## Objectif et historique utile

CreditFlow est une application locale de visualisation du parcours de crédit : étapes, équipes contributrices et connexions orientées. Les utilisateurs sont francophones. L’utilisateur a explicitement demandé Python, HTML, CSS et JavaScript navigateur, **sans Node.js**.

Les demandes déjà implémentées sont : comptes administrateur/lecteur ; connexions directes par glisser-déposer ; courbes et styles de lignes persistants ; correction des erreurs d’initialisation et de déconnexion ; durcissement des comptes et de l’API ; interface française ; équipes et sous-équipes avec effectifs ; cinq macro-étapes avec zoom vers les sous-étapes ; cartes de sous-étapes reprenant le format macro avec une identité visuelle différente.

La dernière demande fonctionnelle concernait les **cartes de sous-étapes**. Elle est implémentée. La demande actuelle est de fournir cette passation au prochain modèle ; aucune nouvelle fonctionnalité n’a été décidée.

## Architecture et fichiers

| Fichier | Responsabilité |
| --- | --- |
| `app.py` | Flask, middleware d’authentification/autorisation, API JSON, sessions, migrations initiales, SQLite, serveur Waitress |
| `validation.py` | JSON borné, types stricts, identifiants, textes, couleurs, coordonnées, connexions, effectifs et macro-étapes |
| `hierarchy.py` | Migration idempotente des macro-étapes et sous-équipes, données d’exemple françaises |
| `localization.py` | Traduction des libellés/descriptions de démonstration et catalogue des erreurs |
| `templates/index.html` | Tableau de bord, canevas, panneaux de gestion, formulaire natif de déconnexion |
| `templates/login.html` | Création initiale de l’administrateur et connexion |
| `static/app.js` | Script autonome : rendu DOM/SVG, CRUD, navigation hiérarchique, pan/zoom, déplacement et connexion des cartes |
| `static/login.js` | Logique de connexion et de création initiale |
| `static/styles.css` | Thème, disposition générale, composants historiques |
| `static/access.css` | Comptes, styles du graphe, macros et sous-étapes, hiérarchie des équipes, adaptations responsive |
| `requirements.lock` | Dépendances d’exécution avec versions exactes et hashes |
| `requirements-dev.txt` | Dépendances d’exécution et moteur JavaScript MiniRacer pour les tests |
| `tests/` | Régressions Python/API, sécurité, traduction, logique JS et véritable serveur HTTP temporaire |
| `SECURITY.md` / `SECURITY_REPORT.md` | Configuration de sécurité, responsabilités de déploiement, audit historique et limites |

Stack : Flask, Werkzeug, Jinja, Waitress, SQLite et navigateur natif. Aucun serveur JavaScript, gestionnaire de paquets JS ou étape de compilation.

## Modèle de données et API

- `stages` : nom, description, phase technique, coordonnées `x/y`, `macro_id` nullable.
- `teams` et `stage_teams` : équipes parentes et associations multiples aux étapes.
- `subteams` : `team_id`, nom unique dans son parent, `headcount` entier 0–10 000 et indicateur `is_example`.
- `macro_stages` : nom, description, couleur, ordre d’affichage.
- `edges` : source, cible, libellé, tracé `straight/curved/elbow`, style `solid/dashed/dotted`, couleur, épaisseur et courbure. Pas de boucle sur soi-même ni de doublon orienté.
- Tables de sécurité : `users`, `auth_sessions`, `login_attempts`, `rate_limits`, `security_events` et `settings`.
- `GET /api/journey` fournit `stages`, `teams`, `edges`, `macros`, `subteams`. Chaque équipe inclut ses sous-équipes, un total `headcount` et `has_example_headcounts`. Les étapes/équipes incluent des champs d’affichage français.
- Écritures principales : `/api/stages`, `/api/stages/<id>`, `/api/stages/<id>/position`, `/api/teams`, `/api/teams/<id>`, `/api/edges`, `/api/edges/<id>`, `/api/subteams`, `/api/subteams/<id>`, `/api/macros`, `/api/macros/<id>`.
- Comptes : `/api/auth/session`, `/api/auth/setup`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/password`, `/api/users`, contrôles de comptes et révocation de sessions. Consulter les décorateurs dans `app.py` pour les méthodes exactes.
- Export authentifié : `GET /api/export`. Les exports ne contiennent pas les comptes ni les secrets.

Les suppressions d’équipe retirent aussi ses sous-équipes et associations. La suppression d’une macro met `macro_id` à `NULL` : les étapes et connexions restent présentes. Les limites sont 1 000 étapes, 250 équipes, 5 000 connexions, 250 comptes, 50 macros, 2 000 sous-équipes et 100 sous-équipes par parent.

## Hiérarchie et comportement attendu

Les cinq macro-étapes d’exemple sont :

1. Acquisition et simulation — `Discovery`.
2. Dossier et éligibilité — `Application`.
3. Analyse et décision — `Assessment`.
4. Contractualisation et financement — `Contracting` et `Fulfillment`.
5. Suivi et fidélisation — `Lifecycle`.

La migration utilise le marqueur `settings.hierarchy_v1` et ne doit pas réinjecter les exemples après modification ou suppression. Les étapes hors de ces groupes apparaissent dans la carte virtuelle **Étapes à classer**. Les sous-équipes et effectifs initiaux sont explicitement marqués comme exemples fictifs ; les équipes personnalisées ne reçoivent pas d’effectif inventé. Enregistrer une sous-équipe retire son indicateur d’exemple.

Dans `static/app.js`, `currentMacroId` vaut `null` pour la vue d’ensemble, un identifiant numérique pour un groupe, `'unclassified'` pour les étapes à classer ou `'all'` pour toutes les sous-étapes. Les fonctions importantes sont `visibleStages`, `renderMacroOverview`, `enterMacro`, `returnToOverview`, `renderGraph`, `renderEdges`, `fitGraph`, `renderTeamHierarchy`, `wireHierarchy`.

Le clic sur une macro anime le zoom, puis présente seulement ses sous-étapes. Le retour restaure la caméra. Les transitions respectent la réduction des mouvements et empêchent les navigations concurrentes. La vue d’ensemble agrège les connexions entre groupes. La vue « Toutes les sous-étapes » permet aux administrateurs de créer aussi des connexions entre différents groupes.

Les connexions se créent avec les poignées **+**, par drag/drop ou au clavier. Cliquer un trait ouvre une barre de style compacte avec sauvegarde automatique. Les lecteurs n’ont aucune poignée ni possibilité d’écriture. Déconnexion : formulaire HTML POST `/logout`, indépendant du graphe et de JavaScript.

## Dernier changement UI livré

Les macros conservent leurs cartes blanches de **280 × 180**, accent sur le bord supérieur, titre, description, compteurs et « Explorer ↗ ».

Les sous-étapes utilisent maintenant des cartes de **270 × 180** : fond lavande dégradé, accent violet sur le bord gauche, badge numéroté « SOUS-ÉTAPE 01 », titre, description, compteur d’équipes et « Détails ↗ ». Un point coloré conserve le repère de phase de la légende. Les noms des équipes et leurs effectifs restent dans l’infobulle et dans la fiche détaillée. Le bouton « Afficher les équipes » masque/affiche le compteur sur la carte.

Les nouvelles classes sont `stage-eyebrow`, `stage-phase-dot`, `stage-title`, `stage-description`, `stage-footer`, `stage-enter` et l’ancienne `graph-team-label`. Les constantes `STAGE_WIDTH` et `STAGE_HEIGHT` ainsi que `fitGraph` ont été ajustés pour maintenir les flèches, poignées et zones de dépôt sur les bords réels. Le déplacement des cartes conserve les positions existantes. Les tests de libellés recherchent maintenant `.stage-title` au lieu d’un index d’enfant DOM.

## Lancer et vérifier

Dans cet espace Windows préparé :

```powershell
.\.runtime\python.exe app.py
```

Ou `python app.py`, qui sélectionne automatiquement ce runtime privé s’il existe. Adresse par défaut : **http://127.0.0.1:5001**. Le serveur refuse une seconde instance sur le même port. Vérifier l’instance existante avant de lancer ou redémarrer. Pour des modifications JS/CSS, le serveur déjà lancé sert les nouveaux fichiers sans redémarrage ; recharger la page. Les URL des assets ont un hash de contenu et des en-têtes `no-store`.

Pour un checkout neuf, suivre `README.md` : utiliser un Python maintenu, créer un environnement Python et installer `requirements.lock` avec `--require-hashes`. Le runtime préparé est Python 3.14.10 ; cette version ou une version plus récente est exigée par la configuration de production actuelle.

Suite complète dans cet espace, avec le runtime privé et MiniRacer dans `.venv` :

```powershell
@'
import sys
import unittest
from pathlib import Path
sys.path.append(str(Path('.venv/Lib/site-packages').resolve()))
suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | .\.runtime\python.exe
```

Pour les seuls tests d’interface, remplacer la ligne `suite = ...` par ces deux lignes :

```python
sys.path.insert(0, str(Path('tests').resolve()))
suite = unittest.defaultTestLoader.loadTestsFromNames(['test_frontend', 'test_hierarchy_frontend'])
```

Dans un environnement Python avec les dépendances de développement installées, la commande standard est `python -m unittest discover -s tests -v`.

Les tests API utilisent des bases temporaires et des comptes synthétiques. `test_http_server.py` lance un vrai serveur Waitress sur un port loopback éphémère puis le ferme. Les tests JS utilisent un moteur embarqué Python avec les doubles DOM de `tests/frontend_dom_stub.js`, sans Node ni navigateur réel.

## Validation réellement effectuée

- Avant le dernier changement de cartes : **64 tests dans la suite complète + 2 tests complémentaires**, tous réussis. La suite actuelle contient donc 66 tests.
- Après le dernier changement de cartes : **20 tests d’interface**, tous réussis, couvrant aussi pan/zoom, drag/drop, annulation/restauration, permissions et navigation. Les 66 tests n’ont pas été tous relancés après cette seule retouche JS/CSS.
- Les fichiers JS/CSS mis à jour ont été téléchargés depuis le serveur local et comparés aux fichiers du disque. Dimensions CSS/JS vérifiées identiques.
- Lors du déploiement de la hiérarchie : sauvegarde SQLite cohérente puis vérification des digests des anciennes colonnes d’étapes, des équipes, connexions, associations, comptes et clé de session. Valeurs préexistantes conservées ; intégrité et clés étrangères vérifiées.
- Instantané de cette migration : 9 étapes, 9 équipes parentes, 6 connexions, 21 associations étape/équipe ; ajout de 5 macros et 17 sous-équipes d’exemple. Ces nombres peuvent changer avec les modifications de l’utilisateur.
- Les résultats locaux de migration se trouvent dans `security-scan-results/hierarchy-data-baseline.json` et `hierarchy-live-check.json`. Le dossier est ignoré par Git et peut manquer dans un transfert.
- **Pas de validation visuelle navigateur** : l’outil d’automatisation n’avait ni navigateur ni connexion native disponible. Ne pas présenter les tests DOM comme une capture ou un contrôle visuel.

## Sécurité et points de vigilance

L’API authentifie les utilisateurs, vérifie les rôles pour chaque écriture et exige CSRF/origine valide. Sessions aléatoires adossées à des tokens hashés en base, expiration de 8 h d’inactivité / 24 h absolues, déconnexion révocable, changement de mot de passe et désactivation de compte avec révocation. Le dernier administrateur actif est protégé.

JSON, identifiants, types, chaînes, couleurs et nombres sont bornés. Requêtes SQL paramétrées ; données utilisateur rendues en texte. CSP locale, liste limitée de fichiers statiques publics, restrictions d’hôte et en-têtes de sécurité sont en place. Ne pas désactiver ces contrôles pour faciliter une nouvelle UI.

`SECURITY_REPORT.md` est un **rapport historique**, dont le nombre de tests et l’audit des dépendances correspondent au moment de sa rédaction. Le dernier passage Bandit sur `app.py`, `validation.py`, `hierarchy.py` a seulement relevé B606, gravité faible, sur le remplacement volontaire du processus par le runtime Python local à chemin fixe, sans shell. Aucun nouveau résultat d’audit ne doit être inféré de cette note.

L’application reste locale. L’exposition publique, TLS, proxy, MFA/SSO, récupération de compte, sauvegardes organisationnelles et protection réseau ne sont pas fournis par cette interface. Ne pas promettre une protection absolue ou l’absence de zero-days.

Les données sont dans OneDrive ; `.gitignore` n’empêche pas la synchronisation cloud. Les sauvegardes préparées sont hors OneDrive, sous `%LOCALAPPDATA%\CreditFlow\Backups`, notamment `before-hierarchy-20261108-162705.db`. Ne pas copier les bases ou secrets dans un document destiné à un autre modèle.

## Reprise conseillée

Lire les deux documents d’orientation, confirmer l’état du serveur et la demande suivante de l’utilisateur, puis travailler sur le besoin demandé. Si un navigateur devient disponible, vérifier visuellement les nouvelles cartes aux deux niveaux, leurs longues descriptions, les flèches/poignées, le zoom et l’affichage mobile. Préserver le style des macros que l’utilisateur a explicitement apprécié.
