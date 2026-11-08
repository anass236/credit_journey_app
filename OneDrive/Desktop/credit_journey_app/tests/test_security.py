"""Security regression checks use disposable SQLite databases and test clients."""
import json
import time
import unittest
from unittest.mock import patch

import test_app


class SecurityTests(unittest.TestCase):
    setUpClass = classmethod(test_app.JourneyTests.setUpClass.__func__)
    tearDownClass = classmethod(test_app.JourneyTests.tearDownClass.__func__)
    setUp = test_app.JourneyTests.setUp
    tearDown = test_app.JourneyTests.tearDown
    token = test_app.JourneyTests.token
    send = test_app.JourneyTests.send
    setup_admin = test_app.JourneyTests.setup_admin
    viewer = test_app.JourneyTests.viewer

    def login(self, client=None, username='admin', password='admin-password-123'):
        return self.send('/api/auth/login', payload={'username':username,'password':password}, client=client)

    def test_copied_cookie_cannot_be_replayed_after_api_or_form_logout(self):
        self.setup_admin()
        for mode in ['api', 'form']:
            with self.subTest(mode=mode):
                if mode == 'form':
                    self.assertEqual(self.login().status_code, 200)
                cookie = self.client.get_cookie('session').value
                if mode == 'api':
                    self.assertEqual(self.send('/api/auth/logout').status_code, 200)
                else:
                    self.assertEqual(self.client.post('/logout', data={'csrf_token':self.token()}).status_code, 303)
                attacker = self.app.test_client()
                attacker.set_cookie('session', cookie)
                self.assertEqual(attacker.get('/api/journey').status_code, 401)

    def test_old_user_id_and_fabricated_token_cookies_cannot_authenticate(self):
        self.setup_admin()
        for token in [None, '0' * 64]:
            attacker = self.app.test_client()
            with attacker.session_transaction() as cookie:
                cookie['user_id'] = 1
                if token:
                    cookie['auth_token'] = token
            self.assertEqual(attacker.get('/api/journey').status_code, 401)

    def test_sessions_have_idle_and_absolute_expiry(self):
        self.setup_admin()
        for field in ['expires_at', 'created_at']:
            with self.subTest(field=field):
                if field == 'created_at':
                    self.assertEqual(self.login().status_code, 200)
                with self.module.connection() as db:
                    if field == 'expires_at':
                        db.execute('UPDATE auth_sessions SET expires_at=?', (time.time()-1,))
                    else:
                        db.execute('UPDATE auth_sessions SET created_at=?', (time.time()-25*3600,))
                self.assertEqual(self.client.get('/api/journey').status_code, 401)

    def test_session_tokens_are_hashed_in_database(self):
        self.setup_admin()
        with self.client.session_transaction() as cookie:
            token = cookie['auth_token']
        with self.module.connection() as db:
            stored = db.execute('SELECT token_hash FROM auth_sessions').fetchone()['token_hash']
        self.assertNotEqual(token, stored)
        self.assertEqual(stored, self.module.token_hash(token))

    def test_disabled_account_loses_access_and_cannot_sign_back_in(self):
        viewer = self.viewer()
        uid = next(user['id'] for user in self.client.get('/api/users').json['users'] if user['username']=='viewer')
        self.assertEqual(self.send(f'/api/users/{uid}', 'PATCH', {'disabled':True}).status_code, 200)
        self.assertEqual(viewer.get('/api/journey').status_code, 401)
        self.assertEqual(self.login(viewer, 'viewer', 'viewer-password-123').status_code, 401)
        self.assertEqual(self.send(f'/api/users/{uid}', 'PATCH', {'disabled':False}).status_code, 200)
        self.assertEqual(self.login(viewer, 'viewer', 'viewer-password-123').status_code, 200)

    def test_last_administrator_cannot_be_disabled_or_demoted(self):
        self.setup_admin()
        for payload in [{'disabled':True}, {'role':'viewer'}]:
            self.assertEqual(self.send('/api/users/1', 'PATCH', payload).status_code, 409)
        self.assertEqual(self.client.get('/api/journey').status_code, 200)

    def test_admin_can_revoke_sessions_but_viewer_cannot_manage_access(self):
        viewer = self.viewer()
        uid = next(user['id'] for user in self.client.get('/api/users').json['users'] if user['username']=='viewer')
        self.assertEqual(self.send(f'/api/users/{uid}', 'PATCH', {'role':'admin'}, viewer).status_code, 403)
        self.assertEqual(self.send(f'/api/users/{uid}/revoke-sessions', payload={}, client=viewer).status_code, 403)
        self.assertEqual(viewer.get('/api/security/events').status_code, 403)
        self.assertEqual(self.send(f'/api/users/{uid}/revoke-sessions', payload={}).status_code, 200)
        self.assertEqual(viewer.get('/api/journey').status_code, 401)

    def test_password_change_requires_old_password_and_revokes_all_devices(self):
        viewer = self.viewer()
        device = self.app.test_client()
        self.assertEqual(self.login(device, 'viewer', 'viewer-password-123').status_code, 200)
        payload = {'current_password':'wrong','new_password':'a-new-viewer-password-456'}
        self.assertEqual(self.send('/api/auth/password', payload=payload, client=viewer).status_code, 403)
        payload['current_password'] = 'viewer-password-123'
        self.assertEqual(self.send('/api/auth/password', payload=payload, client=viewer).status_code, 200)
        self.assertEqual(viewer.get('/api/journey').status_code, 401)
        self.assertEqual(device.get('/api/journey').status_code, 401)
        self.assertEqual(self.client.get('/api/journey').status_code, 200)
        self.assertEqual(self.login(device, 'viewer', 'viewer-password-123').status_code, 401)
        self.assertEqual(self.login(device, 'viewer', payload['new_password']).status_code, 200)

    def test_changing_usernames_or_forwarded_ips_cannot_bypass_auth_ip_limit(self):
        self.setup_admin()
        other = self.app.test_client()
        token = self.token(other)
        responses = []
        for index in range(31):
            response = other.post('/api/auth/login', json={'username':f'unknown_{index}', 'password':'wrong'},
                                  headers={'X-CSRF-Token':token,'X-Forwarded-For':f'198.51.100.{index}'})
            responses.append(response)
        self.assertIn(429, [response.status_code for response in responses])
        self.assertEqual(responses[-1].status_code, 429)
        self.assertIn('Retry-After', responses[-1].headers)

    def test_untrusted_hosts_and_cross_origin_writes_are_rejected(self):
        for host in ['attacker.example', 'localhost.attacker.example']:
            self.assertEqual(self.client.get('/login', base_url=f'http://{host}').status_code, 400)
        self.setup_admin()
        token = self.token()
        for headers in [{'Origin':'https://attacker.example'}, {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}]:
            result = self.client.post('/api/teams', json={'name':'Cross-origin'}, headers={'X-CSRF-Token':token,**headers})
            self.assertEqual(result.status_code, 403)
        good = self.client.post('/api/teams', json={'name':'Same-origin'}, headers={'X-CSRF-Token':token,'Origin':'http://localhost'})
        self.assertEqual(good.status_code, 201)

    def test_first_admin_setup_is_local_and_disabled_for_hosted_mode(self):
        token = self.token()
        payload = {'username':'admin','password':'admin-password-123'}
        remote = self.client.post('/api/auth/setup', json=payload, headers={'X-CSRF-Token':token}, environ_overrides={'REMOTE_ADDR':'198.51.100.20'})
        self.assertEqual(remote.status_code, 403)
        with patch.dict(self.app.config, {'ALLOW_WEB_SETUP':False}):
            self.assertEqual(self.send('/api/auth/setup', payload=payload).status_code, 403)
        self.assertTrue(self.client.get('/api/auth/session').json['setup_required'])

    def test_wrong_json_shapes_malformed_json_and_wrong_media_types_never_crash(self):
        self.setup_admin()
        routes = [('POST','/api/stages'),('POST','/api/teams'),('POST','/api/edges'),('POST','/api/users'),
                  ('PUT','/api/stages/1'),('PUT','/api/edges/1'),('PATCH','/api/stages/1/position'),('PATCH','/api/users/1')]
        for method, path in routes:
            for payload in [[], 'text', 1, True, {}]:
                with self.subTest(path=path,payload=payload):
                    self.assertEqual(self.send(path, method, payload).status_code, 400)
        token = self.token()
        for body in ['null','{','{"name":"a","name":"b"}','{"x":NaN}','{"x":Infinity}', '['*2000+'0'+']'*2000]:
            response = self.client.post('/api/stages', data=body, content_type='application/json',headers={'X-CSRF-Token':token})
            self.assertEqual(response.status_code, 400)
        result = self.client.post('/api/teams', data='{}', content_type='text/plain',headers={'X-CSRF-Token':token})
        self.assertEqual(result.status_code, 415)
        result = self.client.post('/api/teams', data='x'*70000, content_type='application/json',headers={'X-CSRF-Token':token})
        self.assertEqual(result.status_code, 413)

    def test_invalid_domain_values_and_huge_numbers_are_rejected(self):
        self.setup_admin()
        examples = [('/api/stages', {'name':None}), ('/api/stages',{'name':{'html':'x'}}),
                    ('/api/stages',{'name':'a'*101}),('/api/stages',{'name':'Okay','phase':'Invented'}),
                    ('/api/stages',{'name':'Okay','team_ids':[True]}),('/api/stages',{'name':'Okay','team_ids':[[1]]}),
                    ('/api/stages',{'name':'Okay','x':10**1000}),('/api/stages',{'name':'Okay','x':'100'}),
                    ('/api/teams',{'name':'Okay','color':'#fff; background:url(https://evil.example)'}),
                    ('/api/edges',{'source':True,'target':2}),('/api/edges',{'source':10**200,'target':2}),
                    ('/api/edges',{'source':1,'target':3,'shape':[]}),('/api/edges',{'source':1,'target':3,'width':10**1000}),
                    ('/api/users',{'username':'okay','password':'a'*129}),('/api/users',{'username':[],'password':'a'*12})]
        for path,payload in examples:
            with self.subTest(path=path,payload=payload):
                self.assertEqual(self.send(path,payload=payload).status_code, 400)
        self.assertEqual(self.send(f'/api/stages/{10**200}', 'DELETE').status_code, 404)

    def test_invalid_team_assignment_rolls_back_the_whole_stage(self):
        self.setup_admin()
        before = len(self.client.get('/api/journey').json['stages'])
        self.assertEqual(self.send('/api/stages',payload={'name':'No orphan','team_ids':[99999]}).status_code, 400)
        self.assertEqual(len(self.client.get('/api/journey').json['stages']),before)

    def test_sql_and_html_payloads_are_data_and_not_markup(self):
        self.setup_admin()
        name = "x'); DROP TABLE users; -- <img src=x onerror=alert(1)>"
        self.assertEqual(self.send('/api/stages',payload={'name':name}).status_code, 201)
        self.assertEqual(self.client.get('/api/journey').json['stages'][-1]['name'],name)
        self.assertEqual(len(self.client.get('/api/users').json['users']),1)
        response = self.client.get('/api/journey')
        self.assertEqual(response.mimetype,'application/json')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')

    def test_sensitive_files_are_not_served(self):
        for path in ['/journey.db','/.env','/app.py','/static/../journey.db','/static/%2e%2e/app.py','/static/NUL']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code,404)

    def test_security_headers_and_hosted_cookie_flags(self):
        response = self.client.get('/login')
        policy = response.headers['Content-Security-Policy']
        for directive in ["script-src 'self'", "frame-ancestors 'none'", "base-uri 'none'", "form-action 'self'"]:
            self.assertIn(directive,policy)
        self.assertNotIn('unsafe-eval',policy)
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        self.assertIn('camera=()',response.headers['Permissions-Policy'])
        self.assertIn('HttpOnly',response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict',response.headers['Set-Cookie'])
        self.assertNotIn('googleapis',response.get_data(as_text=True))
        with patch.dict(self.app.config, {'SESSION_COOKIE_SECURE':True}):
            other = self.app.test_client()
            hosted = other.get('/login',base_url='https://localhost')
            self.assertIn('Secure',hosted.headers['Set-Cookie'])
            self.assertEqual(hosted.headers['Strict-Transport-Security'],'max-age=31536000')

    def test_security_event_log_does_not_contain_credentials(self):
        self.setup_admin()
        with self.client.session_transaction() as cookie:
            token = cookie['auth_token']
        events = self.client.get('/api/security/events').json['events']
        self.assertTrue(events)
        serialized = json.dumps(events)
        self.assertNotIn('admin-password-123',serialized)
        self.assertNotIn(token,serialized)
        self.assertNotIn('password_hash',serialized)


if __name__ == '__main__':
    unittest.main()
