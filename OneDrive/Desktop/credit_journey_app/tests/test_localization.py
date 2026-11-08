"""French UI checks without changing stored account or journey identifiers."""
import ast
from pathlib import Path
import unittest

import test_app
from localization import ERRORS

ROOT = Path(__file__).resolve().parents[1]


class FrenchLocalizationTests(unittest.TestCase):
    setUpClass = classmethod(test_app.JourneyTests.setUpClass.__func__)
    tearDownClass = classmethod(test_app.JourneyTests.tearDownClass.__func__)
    setUp = test_app.JourneyTests.setUp
    tearDown = test_app.JourneyTests.tearDown
    token = test_app.JourneyTests.token
    send = test_app.JourneyTests.send
    setup_admin = test_app.JourneyTests.setup_admin

    def test_french_login_workspace_and_role_labels(self):
        response = self.client.get('/login')
        self.assertIn('<html lang="fr">', response.get_data(as_text=True))
        self.assertEqual(response.headers['Content-Language'], 'fr')
        self.assertIn('Créer votre compte administrateur', response.get_data(as_text=True))
        self.setup_admin()
        html = self.client.get('/').get_data(as_text=True)
        for label in ['Comptes et accès', 'Administrateur', 'Se déconnecter', 'Lecteur', 'value="Discovery">Découverte', 'value="curved">Courbe']:
            self.assertIn(label, html)
        self.assertNotIn('\ufffd', html)
        for label in ['Sign out', 'Add stage', 'Accounts & access', 'Journey overview']:
            self.assertNotIn(label, html)

    def test_default_content_is_translated_without_rewriting_stored_data(self):
        self.setup_admin()
        data = self.client.get('/api/journey').json
        stage = data['stages'][0]
        self.assertEqual(stage['name'], 'Awareness & acquisition')
        self.assertEqual(stage['display_name'], 'Découverte et acquisition')
        self.assertIn('Le client découvre', stage['display_description'])
        team = next(team for team in data['teams'] if team['name'] == 'Credit Risk')
        self.assertEqual(team['display_name'], 'Risque de crédit')
        custom = self.send('/api/stages', payload={'name':'Validation locale personnalisée', 'description':'Texte saisi par le client', 'phase':'Assessment'})
        self.assertEqual(custom.status_code, 201)
        saved = next(stage for stage in self.client.get('/api/journey').json['stages'] if stage['id']==custom.json['id'])
        self.assertEqual(saved['name'], saved['display_name'])
        self.assertEqual(saved['description'], saved['display_description'])
        self.assertEqual(saved['phase'], 'Assessment')
        with self.module.connection() as db:
            self.assertEqual(db.execute('SELECT name FROM stages WHERE id=1').fetchone()['name'], 'Awareness & acquisition')

    def test_error_messages_are_french_and_all_fixed_api_errors_have_translations(self):
        self.assertEqual(self.client.get('/api/journey').json['error'], 'Veuillez vous connecter.')
        self.setup_admin()
        invalid_password = self.send('/api/users', payload={'username':'reader','password':'short'})
        self.assertIn('mot de passe', invalid_password.json['error'])
        self.assertEqual(invalid_password.status_code, 400)
        self.assertEqual(self.client.get('/missing').json['error'], 'Ressource introuvable.')
        tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'invalid' and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.assertIn(node.args[0].value, ERRORS)


if __name__ == '__main__':
    unittest.main()
