"""Exercise the actual Python/Waitress entry point on an ephemeral loopback port."""
import http.cookiejar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class LiveHTTPTests(unittest.TestCase):
    def test_real_server_auth_assets_permissions_and_logout(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            interpreter = ROOT / '.runtime/python.exe'
            if not interpreter.is_file():
                interpreter = Path(sys.executable)
            env = {**os.environ, 'CREDIT_JOURNEY_DB':str(Path(directory)/'http.db'), 'PORT':str(port),
                   'CREDIT_JOURNEY_PRODUCTION':'0', 'CREDIT_JOURNEY_HTTPS':'0',
                   'CREDIT_JOURNEY_TRUSTED_HOSTS':'localhost,127.0.0.1,[::1]'}
            process = subprocess.Popen([str(interpreter), str(ROOT/'app.py')], cwd=ROOT, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                root = f'http://127.0.0.1:{port}'
                jar = http.cookiejar.CookieJar()
                browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

                def request(path, payload=None, token=None, method=None, client=browser, headers=None, form=False):
                    all_headers = dict(headers or {})
                    body = None
                    if payload is not None:
                        body = (urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
                        all_headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
                    if token:
                        all_headers['X-CSRF-Token'] = token
                    req = urllib.request.Request(root+path, data=body, method=method, headers=all_headers)
                    try:
                        response = client.open(req, timeout=5)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        return response.status, response.headers, response.read(), response.geturl()

                for _ in range(100):
                    if process.poll() is not None:
                        self.fail('Server exited: ' + process.stdout.read().decode(errors='replace'))
                    try:
                        state = request('/api/auth/session')
                        break
                    except urllib.error.URLError:
                        time.sleep(.05)
                else:
                    self.fail('Server did not start.')
                csrf = json.loads(state[2])['csrf_token']
                created = request('/api/auth/setup', {'username':'httpadmin','password':'http-admin-password-123'}, csrf)
                self.assertEqual(created[0],201)
                csrf = json.loads(created[2])['csrf_token']
                page = request('/')
                self.assertEqual(page[0],200)
                html = page[2].decode()
                scripts = re.findall(r'<script[^>]+src="([^"]+)"',html)
                self.assertEqual(len(scripts),1)
                self.assertRegex(scripts[0],r'^/static/app\.js\?v=[0-9a-f]{16}$')
                asset = request(scripts[0])
                self.assertEqual(asset[0],200)
                self.assertIn(b'function wireGraph()',asset[2])
                self.assertIn(b'function cancelConnectionDrag()',asset[2])
                self.assertIn("script-src 'self'",page[1]['Content-Security-Policy'])
                self.assertEqual(asset[1]['Cache-Control'],'no-store')
                self.assertNotIn('googleapis',html)
                self.assertEqual(request('/',headers={'Host':'attacker.example'})[0],400)
                self.assertEqual(request('/api/users',{'username':'httpviewer','password':'http-viewer-password-123'},csrf)[0],201)
                viewer = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                viewer_csrf = json.loads(request('/api/auth/session',client=viewer)[2])['csrf_token']
                signed_in = request('/api/auth/login',{'username':'httpviewer','password':'http-viewer-password-123'},viewer_csrf,client=viewer)
                self.assertEqual(signed_in[0],200)
                viewer_csrf = json.loads(signed_in[2])['csrf_token']
                self.assertEqual(request('/api/edges',{'source':1,'target':3},viewer_csrf,client=viewer)[0],403)
                copied_cookie = next(cookie.value for cookie in jar if cookie.name=='session')
                self.assertEqual(request('/api/auth/logout',token=csrf,method='POST')[0],200)
                replay = urllib.request.build_opener()
                self.assertEqual(request('/api/journey',client=replay,headers={'Cookie':'session='+copied_cookie})[0],401)
                viewer_page = request('/',client=viewer)[2].decode()
                form_token = re.search(r'id="signOutForm".*?name="csrf_token" value="([^"]+)"',viewer_page).group(1)
                signed_out = request('/logout',{'csrf_token':form_token},client=viewer,form=True)
                self.assertTrue(signed_out[3].endswith('/login'))
                self.assertEqual(request('/api/journey',client=viewer)[0],401)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()


if __name__ == '__main__':
    unittest.main()
