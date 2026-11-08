import importlib.util
import os
import re
from pathlib import Path
import sqlite3
import socket
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from werkzeug.security import check_password_hash


class JourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial_db = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location('journey_app_under_test', Path(__file__).resolve().parents[1] / 'app.py')
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'CREDIT_JOURNEY_DB': str(Path(cls.initial_db.name) / 'initial.db')}):
            spec.loader.exec_module(cls.module)
        cls.app = cls.module.app
        cls.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.initial_db.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.module.DB_PATH = Path(self.tmp.name) / 'journey.db'
        self.module.init_db()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def token(self, client=None):
        return (client or self.client).get('/api/auth/session').json['csrf_token']

    def send(self, path, method='POST', payload=None, client=None, token=None):
        client = client or self.client
        return client.open(path, method=method, json=payload, headers={'X-CSRF-Token': token or self.token(client)})

    def setup_admin(self):
        result = self.send('/api/auth/setup', payload={'username':'admin', 'password':'admin-password-123'})
        self.assertEqual(result.status_code, 201)
        return result

    def viewer(self):
        self.setup_admin()
        result = self.send('/api/users', payload={'username':'viewer', 'password':'viewer-password-123', 'role':'viewer'})
        self.assertEqual(result.status_code, 201)
        viewer = self.app.test_client()
        result = self.send('/api/auth/login', payload={'username':'viewer', 'password':'viewer-password-123'}, client=viewer)
        self.assertEqual(result.status_code, 200)
        return viewer

    def test_first_run_and_login_page(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertIn('Créer votre compte administrateur', self.client.get('/login').get_data(as_text=True))
        self.assertEqual(self.client.get('/api/journey').status_code, 401)
        self.assertEqual(self.client.get('/api/export').status_code, 401)
        self.setup_admin()
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertFalse(self.client.get('/api/auth/session').json['setup_required'])

    def test_native_sign_out_form_works_without_javascript_for_both_roles(self):
        viewer = self.viewer()
        for role, client in [('admin', self.client), ('viewer', viewer)]:
            with self.subTest(role=role):
                response = client.get('/')
                match = re.search(r'<form class="sign-out-form" id="signOutForm" method="post" action="([^"]+)"><input type="hidden" name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
                self.assertIsNotNone(match)
                self.assertEqual(match[1], '/logout')
                result = client.post(match[1], data={'csrf_token':match[2]})
                self.assertEqual(result.status_code, 303)
                self.assertEqual(result.headers['Location'], '/login')
                self.assertEqual(client.get('/api/journey').status_code, 401)

    def test_native_sign_out_rejects_invalid_csrf(self):
        self.setup_admin()
        self.assertEqual(self.client.post('/logout', data={}).status_code, 403)
        self.assertEqual(self.client.get('/api/journey').status_code, 200)

    def test_workspace_loads_one_complete_versioned_local_script(self):
        self.setup_admin()
        response = self.client.get('/')
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', response.get_data(as_text=True))
        self.assertEqual(len(scripts), 1)
        self.assertRegex(scripts[0], r'^/static/app\.js\?v=[0-9a-f]{16}$')
        script = self.client.get(scripts[0])
        self.addCleanup(script.close)
        self.assertEqual(script.status_code, 200)
        self.assertIn(b'function wireGraph()', script.data)
        self.assertIn(b'function cancelConnectionDrag()', script.data)
        self.assertNotIn(b'cytoscape', script.data)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(script.headers['Cache-Control'], 'no-store')
        self.assertTrue(self.app.config['TEMPLATES_AUTO_RELOAD'])

    def test_second_development_server_is_rejected_when_port_is_busy(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            with self.assertRaisesRegex(SystemExit, 'already in use'):
                self.module.ensure_port_available(listener.getsockname()[1])

    def test_passwords_are_hashed_and_roles_not_client_controlled(self):
        result = self.send('/api/auth/setup', payload={'username':'admin', 'password':'admin-password-123', 'role':'viewer'})
        self.assertEqual(result.json['user']['role'], 'admin')
        with self.module.connection() as db:
            row = db.execute('SELECT * FROM users').fetchone()
            self.assertNotEqual(row['password_hash'], 'admin-password-123')
            self.assertTrue(check_password_hash(row['password_hash'], 'admin-password-123'))
        self.assertNotIn('password_hash', str(self.client.get('/api/users').json))

    def test_setup_cannot_be_reused(self):
        self.setup_admin()
        other = self.app.test_client()
        self.assertEqual(self.send('/api/auth/setup', payload={'username':'intruder','password':'some-password-123'}, client=other).status_code, 409)

    def test_csrf_required_and_rotated(self):
        stale = self.token()
        self.assertEqual(self.client.post('/api/auth/setup', json={'username':'admin','password':'admin-password-123'}).status_code, 403)
        self.setup_admin()
        self.assertNotEqual(stale, self.token())
        self.assertEqual(self.send('/api/teams', payload={'name':'Test'}, token=stale).status_code, 403)
        self.assertEqual(self.client.post('/api/teams', json={'name':'Test'}, headers={'X-CSRF-Token':'é'}).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 403)

    def test_viewers_can_read_and_export_but_cannot_mutate_any_resource(self):
        viewer = self.viewer()
        self.assertEqual(viewer.get('/api/journey').status_code, 200)
        self.assertEqual(viewer.get('/api/export').status_code, 200)
        self.assertEqual(viewer.get('/api/users').status_code, 403)
        routes = [('POST','/api/stages'), ('PUT','/api/stages/1'), ('PATCH','/api/stages/1/position'),
                  ('DELETE','/api/stages/1'), ('POST','/api/teams'), ('DELETE','/api/teams/1'),
                  ('POST','/api/edges'), ('PUT','/api/edges/1'), ('DELETE','/api/edges/1'), ('POST','/api/users')]
        before = viewer.get('/api/journey').json
        for method, route in routes:
            with self.subTest(route=route, method=method):
                self.assertEqual(self.send(route, method, {}, viewer).status_code, 403)
        self.assertEqual(before, viewer.get('/api/journey').json)
        self.assertEqual(self.send('/api/auth/logout', client=viewer).status_code, 200)
        self.assertEqual(viewer.get('/api/journey').status_code, 401)

    def test_anonymous_cannot_mutate_resources(self):
        self.assertEqual(self.send('/api/stages', payload={}).status_code, 401)
        self.assertEqual(self.send('/api/users', payload={}).status_code, 401)

    def test_invalid_credentials_and_login_throttle(self):
        self.setup_admin()
        other = self.app.test_client()
        for _ in range(10):
            self.assertEqual(self.send('/api/auth/login', payload={'username':'admin','password':'wrong'}, client=other).status_code, 401)
        self.assertEqual(self.send('/api/auth/login', payload={'username':'admin','password':'admin-password-123'}, client=other).status_code, 429)

    def test_account_creation_validation_and_case_insensitive_login(self):
        self.setup_admin()
        self.assertEqual(self.send('/api/users', payload={'username':'short','password':'short'}).status_code, 400)
        self.assertEqual(self.send('/api/users', payload={'username':'viewer','password':'viewer-password-123','role':'owner'}).status_code, 400)
        self.assertEqual(self.send('/api/users', payload={'username':'ADMIN','password':'viewer-password-123'}).status_code, 409)
        self.assertEqual(self.send('/api/users', payload={'username':'Reader','password':'viewer-password-123'}).status_code, 201)
        other = self.app.test_client()
        self.assertEqual(self.send('/api/auth/login', payload={'username':'reader','password':'viewer-password-123'}, client=other).json['user']['role'], 'viewer')

    def test_admin_crud_and_position_preservation(self):
        self.setup_admin()
        team = self.send('/api/teams', payload={'name':'New team','color':'#123456'}).json['id']
        stage = {'name':'New stage','description':'Test','phase':'Discovery','x':100,'y':200,'team_ids':[team]}
        result = self.send('/api/stages', payload=stage)
        self.assertEqual(result.status_code, 201)
        sid = result.json['id']
        self.assertEqual(self.send(f'/api/stages/{sid}/position', 'PATCH', {'x':450,'y':250}).status_code, 200)
        stage.update(x=450,y=250,name='Updated')
        self.assertEqual(self.send(f'/api/stages/{sid}', 'PUT', stage).status_code, 200)
        saved = next(s for s in self.client.get('/api/journey').json['stages'] if s['id']==sid)
        self.assertEqual((saved['x'],saved['y'],saved['team_ids']), (450,250,[team]))
        self.assertEqual(self.send(f'/api/stages/{sid}', 'DELETE').status_code, 200)
        self.assertEqual(self.send(f'/api/teams/{team}', 'DELETE').status_code, 200)

    def test_connection_styles_persist_update_and_export(self):
        self.setup_admin()
        payload = {'source':1,'target':3,'label':'Approved','shape':'curved','line_style':'dashed','color':'#123456','width':4.5,'bend':-120}
        result = self.send('/api/edges', payload=payload)
        self.assertEqual(result.status_code, 201)
        eid = result.json['id']
        for shape in ['curved', 'elbow', 'straight']:
            payload['shape'] = shape
            self.assertEqual(self.send(f'/api/edges/{eid}', 'PUT', payload).status_code, 200)
            saved = next(e for e in self.client.get('/api/export').json['edges'] if e['id']==eid)
            for key,value in payload.items():
                self.assertEqual(saved[key], value)
        self.module.init_db()
        self.assertEqual(next(e for e in self.module.get_data()['edges'] if e['id']==eid)['shape'], 'straight')

    def test_invalid_connection_styles_are_rejected(self):
        self.setup_admin()
        base = {'source':1,'target':3}
        for invalid in [{'shape':'unknown'}, {'color':'red'}, {'width':9}, {'width':float('inf')}, {'bend':float('nan')}, {'line_style':'custom'}, {'source':1,'target':1}]:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.send('/api/edges', payload={**base,**invalid}).status_code, 400)
        self.assertEqual(self.send('/api/edges/999', 'PUT', base).status_code, 404)

    def test_legacy_database_migration_preserves_diagram(self):
        legacy_path = Path(self.tmp.name) / 'legacy.db'
        with closing(sqlite3.connect(legacy_path)) as db:
            db.executescript("""
                CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT, color TEXT);
                CREATE TABLE stages(id INTEGER PRIMARY KEY, name TEXT, description TEXT, phase TEXT, x REAL, y REAL);
                CREATE TABLE edges(id INTEGER PRIMARY KEY, source INTEGER, target INTEGER, label TEXT);
                INSERT INTO teams VALUES(42,'Existing team','#123456');
                INSERT INTO stages VALUES(10,'Existing stage','','Discovery',125,250);
                INSERT INTO stages VALUES(11,'Next stage','','Other',400,300);
                INSERT INTO edges VALUES(99,10,11,'Existing label');
            """)
            db.commit()
        self.module.DB_PATH = legacy_path
        self.module.init_db()
        self.module.init_db()
        data = self.module.get_data()
        self.assertEqual([s['id'] for s in data['stages']], [10,11])
        self.assertEqual(data['teams'][0]['name'], 'Existing team')
        self.assertEqual(data['edges'][0]['label'], 'Existing label')
        self.assertEqual(data['edges'][0]['shape'], 'curved')
        self.assertEqual(data['stages'][0]['x'], 125)

    def test_sessions_survive_restart_and_role_is_rechecked(self):
        self.setup_admin()
        secret = self.app.config['SECRET_KEY']
        self.module.init_db()
        self.assertEqual(secret, self.app.config['SECRET_KEY'])
        self.assertEqual(self.client.get('/api/journey').status_code, 200)
        with self.module.connection() as db:
            db.execute("UPDATE users SET role='viewer' WHERE username='admin'")
        self.assertEqual(self.send('/api/teams', payload={'name':'Nope'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
