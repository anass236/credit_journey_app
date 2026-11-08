"""Idempotent hierarchy migration; existing journey and account values are preserved."""
from localization import display_text

MACROS = [
    ('Acquisition et simulation', 'Faire connaître l’offre et préparer le projet de financement.', '#22b5be', ['Discovery']),
    ('Dossier et éligibilité', 'Recueillir la demande et vérifier la complétude du dossier.', '#a78bfa', ['Application']),
    ('Analyse et décision', 'Évaluer le risque, réaliser les contrôles et statuer sur la demande.', '#f59e0b', ['Assessment']),
    ('Contractualisation et financement', 'Formaliser l’accord et mettre les fonds à disposition.', '#3b82f6', ['Contracting', 'Fulfillment']),
    ('Suivi et fidélisation', 'Accompagner le client pendant toute la vie du crédit.', '#fb7185', ['Lifecycle']),
]
SUBTEAMS = {
    'Marketing': [('Acquisition digitale', 6), ('Contenu et communication', 4), ('Études et CRM', 3)],
    'Digital & UX': [('Parcours numériques', 5), ('Recherche utilisateur', 3)],
    'Sales': [('Conseillers crédit', 8), ('Partenariats', 4)],
    'Credit Risk': [('Analyse crédit', 6), ('Modèles et décision', 3)],
    'Compliance': [('Connaissance client et conformité', 4), ('Prévention de la fraude', 3)],
    'Operations': [('Production crédit', 7), ('Versements et contrats', 4)],
    'Customer Service': [('Assistance client', 6), ('Suivi des remboursements', 5)],
    'IT & Data': [('Support applicatif', 4), ('Données et reporting', 5)],
}


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS macro_stages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#22b5be',
        sort_order INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE IF NOT EXISTS subteams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        name TEXT NOT NULL, headcount INTEGER NOT NULL DEFAULT 0 CHECK(headcount BETWEEN 0 AND 10000),
        is_example INTEGER NOT NULL DEFAULT 0 CHECK(is_example IN (0,1)),
        UNIQUE(team_id,name COLLATE NOCASE))''')
    if 'macro_id' not in {row['name'] for row in db.execute('PRAGMA table_info(stages)')}:
        db.execute('ALTER TABLE stages ADD COLUMN macro_id INTEGER REFERENCES macro_stages(id) ON DELETE SET NULL')
    db.execute('CREATE INDEX IF NOT EXISTS stages_macro ON stages(macro_id)')
    db.execute('CREATE INDEX IF NOT EXISTS subteams_parent ON subteams(team_id)')
    if db.execute("SELECT 1 FROM settings WHERE key='hierarchy_v1'").fetchone():
        return
    for order, (name, description, color, phases) in enumerate(MACROS, 1):
        cur = db.execute('INSERT INTO macro_stages(name,description,color,sort_order) VALUES (?,?,?,?)', (name, description, color, order))
        for phase in phases:
            db.execute('UPDATE stages SET macro_id=? WHERE macro_id IS NULL AND phase=?', (cur.lastrowid, phase))
    definitions = {display_text(name): children for name, children in SUBTEAMS.items()}
    for team in db.execute('SELECT id,name FROM teams').fetchall():
        for name, headcount in definitions.get(display_text(team['name']), []):
            db.execute('INSERT INTO subteams(team_id,name,headcount,is_example) VALUES (?,?,?,1)', (team['id'], name, headcount))
    db.execute("INSERT INTO settings(key,value) VALUES ('hierarchy_v1','1')")
