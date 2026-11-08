# CreditFlow — Credit Journey Studio

A customizable customer credit-journey visualization and team ownership app.

Pour reprendre ce projet avec un autre modèle ou agent, lire [AGENTS.md](AGENTS.md), puis [HANDOFF.md](HANDOFF.md) : contraintes utilisateur, architecture, état livré et vérifications disponibles.

## Interface en français

L’application est destinée aux utilisateurs francophones : connexion, gestion des comptes, formulaires, messages, aide, rôles, phases et options de liaison sont affichés en français. Les libellés et descriptions du parcours fournis par défaut sont également traduits à l’affichage.

Les données personnalisées, les identifiants, les permissions et les valeurs techniques de l’API sont conservés. Les champs `display_name` et `display_description` fournissent les libellés français ; les champs d’origine restent disponibles pour les exports et les intégrations. Le catalogue se trouve dans `localization.py`.

## Équipes, sous-équipes et effectifs

Ouvrez **Équipes et effectifs**, puis dépliez une équipe pour voir ses sous-équipes et leur nombre de personnes. L’effectif de l’équipe parente est la somme des effectifs renseignés dans ses sous-équipes ; il ne représente pas un décompte de personnes uniques entre différentes équipes. Une équipe sans sous-équipe affiche « effectif à renseigner ».

L’administrateur peut créer, modifier, déplacer vers une autre équipe ou supprimer une sous-équipe. Le champ **Nombre de personnes** accepte un entier de 0 à 10 000. Les lecteurs peuvent consulter cette organisation, sans la modifier. Les fiches des étapes détaillent aussi l’organisation des équipes sélectionnées.

Des sous-équipes et effectifs **fictifs**, marqués **Exemple**, illustrent les équipes fournies par défaut (par exemple, Marketing compte 13 personnes). Enregistrez chaque sous-équipe pour remplacer son exemple par vos données réelles. Vos équipes personnalisées sont conservées sans effectif inventé. La migration est exécutée une seule fois : vos modifications et suppressions ne sont pas écrasées au redémarrage.

## Macro-étapes et zoom

La vue d’ensemble présente cinq macro-étapes d’exemple : **Acquisition et simulation**, **Dossier et éligibilité**, **Analyse et décision**, **Contractualisation et financement**, **Suivi et fidélisation**. Les étapes existantes sont regroupées selon leur phase initiale ; leurs positions, équipes et liaisons sont conservées.

Cliquez sur une carte pour zoomer vers ses sous-étapes. Le bouton **← Vue d’ensemble** revient aux macro-étapes et restaure le cadrage. L’animation respecte la préférence système de réduction des mouvements. Les flèches entre macro-étapes totalisent les liaisons existantes entre leurs sous-étapes.

La vue **Toutes les sous-étapes** permet de voir et de créer des liaisons entre différents groupes, toujours par glisser-déposer et uniquement pour les administrateurs. Ceux-ci peuvent gérer les noms, descriptions, couleurs et l’ordre des macro-étapes via **Gérer les macro-étapes**, et changer l’association depuis la fiche d’une sous-étape. Supprimer une macro-étape conserve ses sous-étapes et leurs liaisons dans **Étapes à classer**.

## Quick start

1. Use a current patched Python (3.14.10 or newer is required for production). This prepared Windows workspace already includes a private Python 3.14.10 runtime under `.runtime`; `python app.py` automatically uses it.
2. Open a terminal in this folder.
3. Run:

```bash
python app.py
```

4. Ouvrez http://127.0.0.1:5001 (ou le port défini avec la variable `PORT`).

5. On the first visit, create your administrator username and password (at least 12 characters). There are no default credentials. Existing journey data is kept and its database is migrated automatically.

For a fresh checkout without the private runtime, create a virtual environment with a patched Python and install the checked, hash-locked runtime dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe app.py
```

The server uses Waitress and stays bound to `127.0.0.1`. There is no interactive debugger. See [SECURITY.md](SECURITY.md) and [the security review](SECURITY_REPORT.md).

## Accounts and access

- Everyone must sign in to view the journey or export it.
- **Admin** accounts can add, edit, delete, and move stages; manage teams and connections; and create accounts.
- **Viewer** accounts can inspect stage details and ownership, pan/zoom, toggle team labels, and export JSON. They cannot change any journey data, including stage positions. The server enforces these restrictions on every write endpoint.
- Sign in as an admin, open **Accounts & access** (or **Accounts** on mobile), and create an account with the Viewer or Admin role. New accounts default to Viewer. There is no public registration.
- Passwords are stored as salted hashes. Sign-in attempts are throttled by account/IP and by IP across usernames. Sessions expire after eight hours of inactivity or 24 hours total, and write requests require a CSRF token and same-origin browser requests.
- Sessions have server-side revocation. Signing out invalidates a copied cookie as well. **Password** changes your password and signs out every device.
- Admins can disable/re-enable accounts and revoke their sessions under **Accounts & access**. The last active administrator cannot be disabled or demoted.
- **Sign out** uses a CSRF-protected Python form and works even if JavaScript or the diagram fails to load.

## Drag-and-drop connections

As an admin, drag the **+** handle on the right side of one stage onto another stage and release. A preview follows the pointer, and a valid destination is highlighted. The directed connection saves immediately with a curved line; no form or confirmation is needed. Drag the card itself to reposition it. This also works with touch input and after panning or zooming. Press **Escape**, release over empty space, or cancel the pointer gesture to stop without creating a line. Duplicate connections and connections to the same stage are rejected.

For keyboard use, focus the source stage's **+** handle and press Enter, then activate the destination stage's **+** handle. Viewers have no connection handles and cannot create or change connections through the API.

Click an existing line to show its compact inline toolbar. Choose **Curved**, **Elbow**, or **Straight**, or adjust the label, color, width, pattern, and curve bend. Changes save automatically. **Remove line** deletes the selected connection. There is no connection modal or source/destination form.

## Capabilities

- Add, edit, delete and reposition credit-journey stages.
- Create and delete teams and assign multiple teams to each stage.
- Draw and remove directed handoff connections, including branching flows.
- Connect stages directly by dragging between them (admin only).
- Customize and edit curved, elbow, and straight connections with persistent line styles.
- Sign in with administrator or read-only viewer accounts.
- Interactive pan/zoom canvas and optional team labels.
- Export the whole model as JSON.
- Persist changes locally in SQLite (`journey.db` auto-created on first run).
- Customize visual theme and responsive layout using `static/styles.css` (see `:root` tokens).

The initial diagram is **illustrative**, not a prescribed credit approval workflow. Adapt it to your organization's actual process and compliance requirements.

## Stack

Python (Flask), SQLite, vanilla JavaScript, native SVG, HTML, and CSS. There is no JavaScript framework, package manager, build step, or JavaScript server.

The diagram uses native browser DOM, SVG, and Pointer Events. All scripts, styles, and fonts use local files or system fonts. No external JavaScript or font service is requested.

## Files

- `app.py`: REST API, validation, seed data and persistence
- `validation.py`: bounded JSON parsing and strict field validation
- `localization.py`: French error messages and default journey display labels
- `hierarchy.py`: one-time macro-stage and subteam migration, with labeled example headcounts
- `requirements.lock`: pinned runtime dependencies with package hashes
- `templates/index.html`: interface markup
- `static/styles.css`: visual design system
- `static/app.js`: one self-contained local script for native DOM/SVG rendering, CRUD, pan/zoom, and admin drag-and-drop connections
- `templates/login.html` and `static/login.js`: first-run setup and sign-in
- `static/access.css`: account, login, and connection-style controls
- `tests/test_app.py`: authentication, permissions, migration, and persistence regression tests
- `tests/test_security.py`: session replay, account controls, injection, resource limits, host/origin, and security-header regression tests
- `tests/test_hierarchy.py` and `tests/test_hierarchy_frontend.py`: hierarchy persistence, admin permissions, staff totals, scoped navigation, and camera restoration

## Verification

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and do not change `journey.db`.

Optional JavaScript logic checks also run through Python:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

These checks embed a JavaScript engine in Python and use small browser API doubles. They verify native SVG routes, drag/drop, pan/zoom coordinates, stage movement, cancellation, failed saves, and viewer restrictions. They do not replace a visual browser check.

Browser checks: sign in as an admin, drag a stage's **+** handle onto a different stage, and verify that a curved connection appears without a form. Repeat after panning and zooming, cancel with Escape, and try an existing connection or the same stage. Select a line to change its style. Sign in as a viewer and verify that handles and editing controls are absent.

In local mode, templates reload automatically when edited, and script/CSS URLs include content versions to avoid mixing old pages with updated code. If a tab was left open during an update, reload it once with **Ctrl+F5**. Only the single local workspace script is loaded; no external diagram library is used.

Run one server at a time. Startup refuses to launch a second copy on an occupied port. Stop the running server with **Ctrl+C** before restarting after Python changes.

## Production notes

For hosting, first create the administrator locally, then configure `CREDIT_JOURNEY_PRODUCTION=1`, `CREDIT_JOURNEY_HTTPS=1`, and `CREDIT_JOURNEY_TRUSTED_HOSTS` with your exact hostname(s). Production refuses unsafe configuration and disables web setup. Place the loopback-only Waitress server behind a maintained HTTPS reverse proxy; these flags do not create a TLS certificate or publicly deploy the app. See [SECURITY.md](SECURITY.md) for proxy, backup, secret, and update requirements.
