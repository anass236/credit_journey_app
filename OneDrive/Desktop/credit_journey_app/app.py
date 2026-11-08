from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import socket
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRIVATE_PYTHON = BASE / '.runtime' / 'python.exe'
if __name__ == '__main__' and os.name == 'nt' and PRIVATE_PYTHON.is_file() and Path(sys.executable).resolve() != PRIVATE_PYTHON.resolve():
    # Fixed project-local interpreter and argument list; no shell is involved.
    os.execv(str(PRIVATE_PYTHON), [str(PRIVATE_PYTHON), str(BASE / 'app.py'), *sys.argv[1:]])

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException
from werkzeug.routing import IntegerConverter, ValidationError as RouteValidationError

import validation
import hierarchy
from localization import display_text, error_text

PUBLIC_ASSETS = {'app.js', 'login.js', 'styles.css', 'access.css'}
DB_PATH = Path(os.environ.get('CREDIT_JOURNEY_DB', str(BASE / 'journey.db')))
app = Flask(__name__)


class RecordIDConverter(IntegerConverter):
    regex = r'[0-9]{1,10}'

    def to_python(self, value):
        value = super().to_python(value)
        if not 1 <= value <= 2147483647:
            raise RouteValidationError()
        return value


app.url_map.converters['int'] = RecordIDConverter
PRODUCTION = os.environ.get('CREDIT_JOURNEY_PRODUCTION') == '1'
if PRODUCTION and sys.version_info < (3, 14, 10):
    raise RuntimeError('Production requires Python 3.14.10 or newer. Use the private app runtime or update Python.')
TRUSTED_HOSTS = [host.strip() for host in os.environ.get('CREDIT_JOURNEY_TRUSTED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',') if host.strip()]
if not TRUSTED_HOSTS or any('*' in host or '/' in host or host.startswith('.') for host in TRUSTED_HOSTS):
    raise RuntimeError('Configure exact trusted hostnames.')
if PRODUCTION and (os.environ.get('CREDIT_JOURNEY_HTTPS') != '1' or not os.environ.get('CREDIT_JOURNEY_TRUSTED_HOSTS')):
    raise RuntimeError('Production requires HTTPS and explicitly configured trusted hosts.')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                  SESSION_COOKIE_SECURE=os.environ.get('CREDIT_JOURNEY_HTTPS') == '1',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=64 * 1024,
                  TEMPLATES_AUTO_RELOAD=not PRODUCTION, SEND_FILE_MAX_AGE_DEFAULT=0,
                  MAX_FORM_MEMORY_SIZE=8192, MAX_FORM_PARTS=10, TRUSTED_HOSTS=TRUSTED_HOSTS,
                  SESSION_IDLE_SECONDS=8 * 3600, SESSION_ABSOLUTE_SECONDS=24 * 3600,
                  ALLOW_WEB_SETUP=not PRODUCTION, DEBUG=False)


@app.template_global()
def asset_url(filename):
    if filename not in PUBLIC_ASSETS:
        raise ValueError('Unknown browser asset.')
    version = hashlib.sha256((BASE / 'static' / filename).read_bytes()).hexdigest()[:16]
    return url_for('static', filename=filename, v=version)

SEED_TEAMS = [
    ('Marketing', '#38BDF8'), ('Digital & UX', '#A78BFA'), ('Sales', '#F59E0B'),
    ('Credit Risk', '#FB7185'), ('Compliance', '#34D399'),
    ('Operations', '#22D3EE'), ('Customer Service', '#F472B6'),
    ('IT & Data', '#94A3B8'),
]
SEED_STAGES = [
    ('Awareness & acquisition', 'Customer discovers our credit offer and enters the funnel.', 'Discovery', 140, 170, ['Marketing', 'Digital & UX']),
    ('Credit simulation', 'Customer estimates installments and checks affordability.', 'Discovery', 430, 170, ['Digital & UX', 'IT & Data']),
    ('Application submission', 'Customer provides identity, financial details, and consent.', 'Application', 720, 170, ['Sales', 'Digital & UX', 'Compliance']),
    ('Identity & fraud checks', 'Verify identity, basic eligibility, and potential fraud signals.', 'Assessment', 1010, 170, ['Compliance', 'Credit Risk', 'IT & Data']),
    ('Credit decision', 'Review creditworthiness and issue a decision.', 'Assessment', 1010, 430, ['Credit Risk', 'IT & Data']),
    ('Offer & e-signature', 'Present terms and capture agreement.', 'Contracting', 720, 430, ['Sales', 'Compliance', 'Digital & UX']),
    ('Funding', 'Release approved funds and communicate completion.', 'Fulfillment', 430, 430, ['Operations', 'IT & Data']),
    ('Servicing & support', 'Manage payments, account requests, and assistance.', 'Lifecycle', 140, 430, ['Operations', 'Customer Service']),
]

@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
        db.commit()
    finally:
        db.close()


def init_db():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','viewer')),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS login_attempts (identity TEXT NOT NULL, attempted_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS login_attempts_lookup ON login_attempts(identity,attempted_at);
        CREATE INDEX IF NOT EXISTS login_attempts_expiry ON login_attempts(attempted_at);
        CREATE TABLE IF NOT EXISTS auth_sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at REAL NOT NULL, last_seen REAL NOT NULL, expires_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at);
        CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id);
        CREATE TABLE IF NOT EXISTS rate_limits (
          bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, resets_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS rate_limits_expiry ON rate_limits(resets_at);
        CREATE TABLE IF NOT EXISTS security_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT NOT NULL,
          target_id INTEGER, status INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS teams (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, color TEXT NOT NULL DEFAULT '#38BDF8'
        );
        CREATE TABLE IF NOT EXISTS stages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          phase TEXT NOT NULL DEFAULT 'Other', x REAL NOT NULL DEFAULT 100, y REAL NOT NULL DEFAULT 100
        );
        CREATE TABLE IF NOT EXISTS stage_teams (
          stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
          team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
          PRIMARY KEY (stage_id,team_id)
        );
        CREATE TABLE IF NOT EXISTS edges (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
          target INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
          label TEXT NOT NULL DEFAULT '',
          UNIQUE (source,target), CHECK (source <> target)
        );
        ''')
        if 'disabled' not in {row['name'] for row in db.execute('PRAGMA table_info(users)')}:
            db.execute('ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(edges)')}
        for name, definition in {
            'shape': "TEXT NOT NULL DEFAULT 'curved'",
            'line_style': "TEXT NOT NULL DEFAULT 'solid'",
            'color': "TEXT NOT NULL DEFAULT '#a9c1c7'",
            'width': 'REAL NOT NULL DEFAULT 2.3',
            'bend': 'REAL NOT NULL DEFAULT 80',
        }.items():
            if name not in columns:
                db.execute(f'ALTER TABLE edges ADD COLUMN {name} {definition}')
        db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)', ('session_secret', secrets.token_hex(32)))
        secret = os.environ.get('CREDIT_JOURNEY_SECRET')
        if secret is not None and len(secret) < 32:
            raise RuntimeError('CREDIT_JOURNEY_SECRET must contain at least 32 random characters.')
        app.config['SECRET_KEY'] = secret or db.execute("SELECT value FROM settings WHERE key='session_secret'").fetchone()['value']
        if db.execute('SELECT COUNT(*) FROM teams').fetchone()[0] == 0 and db.execute('SELECT COUNT(*) FROM stages').fetchone()[0] == 0:
            for name, color in SEED_TEAMS:
                db.execute('INSERT INTO teams(name,color) VALUES (?,?)', (name,color))
            team_ids = {r['name']: r['id'] for r in db.execute('SELECT id,name FROM teams')}
            ids = []
            for name,desc,phase,x,y,teams in SEED_STAGES:
                cur = db.execute('INSERT INTO stages(name,description,phase,x,y) VALUES (?,?,?,?,?)',(name,desc,phase,x,y))
                sid = cur.lastrowid
                ids.append(sid)
                for team in teams:
                    db.execute('INSERT INTO stage_teams(stage_id,team_id) VALUES (?,?)',(sid,team_ids[team]))
            for source,target in zip(ids, ids[1:]):
                db.execute('INSERT INTO edges(source,target) VALUES (?,?)',(source,target))
        hierarchy.initialize(db)


def get_data():
    with connection() as db:
        stages = [dict(r) for r in db.execute('SELECT * FROM stages ORDER BY id')]
        teams = [dict(r) for r in db.execute('SELECT * FROM teams ORDER BY name')]
        edges = [dict(r) for r in db.execute('SELECT * FROM edges ORDER BY id')]
        macros = [dict(r) for r in db.execute('SELECT * FROM macro_stages ORDER BY sort_order,id')]
        subteams = [dict(r) for r in db.execute('SELECT * FROM subteams ORDER BY name,id')]
        memberships = {}
        for row in db.execute('SELECT stage_id,team_id FROM stage_teams'):
            memberships.setdefault(row['stage_id'], []).append(row['team_id'])
        for stage in stages:
            stage['team_ids'] = memberships.get(stage['id'], [])
            stage['display_name'] = display_text(stage['name'])
            stage['display_description'] = display_text(stage['description'])
        for team in teams:
            team['display_name'] = display_text(team['name'])
            team['subteams'] = [subteam for subteam in subteams if subteam['team_id'] == team['id']]
            team['headcount'] = sum(subteam['headcount'] for subteam in team['subteams'])
            team['has_example_headcounts'] = any(subteam['is_example'] for subteam in team['subteams'])
        return {'stages':stages,'teams':teams,'edges':edges,'macros':macros,'subteams':subteams}


def invalid(msg, status=400):
    return jsonify({'error':error_text(msg)}), status


def csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def setup_required():
    with connection() as db:
        return db.execute('SELECT 1 FROM users LIMIT 1').fetchone() is None


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def consume_limit(scope, subject, limit, seconds):
    now = time.time()
    bucket = hmac.new(app.config['SECRET_KEY'].encode(), f'{scope}:{subject}'.encode(), hashlib.sha256).hexdigest()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM rate_limits WHERE resets_at<=?', (now,))
        row = db.execute('SELECT count,resets_at FROM rate_limits WHERE bucket=?', (bucket,)).fetchone()
        if row and row['count'] >= limit:
            response, status = invalid('Too many requests. Try again later.', 429)
            response.headers['Retry-After'] = str(max(1, int(row['resets_at'] - now)))
            return response, status
        db.execute('INSERT INTO rate_limits(bucket,count,resets_at) VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (bucket, now + seconds))
    return None


def revoke_current_session():
    token = session.get('auth_token')
    if isinstance(token, str):
        with connection() as db:
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (token_hash(token),))
    session.clear()


@app.before_request
def authorize():
    g.user = None
    g.payload = None
    if request.endpoint == 'static' and (request.view_args or {}).get('filename') not in PUBLIC_ASSETS:
        return invalid('Not found.', 404)
    for value in (request.view_args or {}).values():
        if isinstance(value, int):
            validation.identifier(value)
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin != request.host_url.rstrip('/')):
            return invalid('Cross-origin changes are not allowed.', 403)
    token = session.get('auth_token')
    if isinstance(token, str) and len(token) == 64:
        now = time.time()
        with connection() as db:
            row = db.execute('SELECT u.id,u.username,u.role FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND s.created_at>? AND u.disabled=0',
                             (token_hash(token), now, now - app.config['SESSION_ABSOLUTE_SECONDS'])).fetchone()
            if row:
                g.user = dict(row)
                db.execute('UPDATE auth_sessions SET last_seen=?,expires_at=MIN(?,created_at+?) WHERE token_hash=?',
                           (now, now + app.config['SESSION_IDLE_SECONDS'], app.config['SESSION_ABSOLUTE_SECONDS'], token_hash(token)))
            else:
                db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (token_hash(token),))
        if not g.user:
            session.clear()
    elif session.get('user_id') or token:
        # Old signed user IDs and forged cookies cannot grant access by themselves.
        session.clear()
    if request.path.startswith('/api/'):
        public = request.endpoint in {'auth_session', 'login', 'setup'}
        if not public and not g.user:
            return invalid('Please sign in.', 401)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if not public and request.endpoint not in {'logout', 'change_password'} and g.user['role'] != 'admin':
                return invalid('Only administrators can change the journey or manage accounts.', 403)
            token = request.headers.get('X-CSRF-Token', '')
            if not token or not secrets.compare_digest(token.encode(), session.get('csrf_token', '').encode()):
                return invalid('Your session has changed. Reload the page and try again.', 403)
            if request.endpoint in {'login', 'setup', 'change_password'}:
                limited = consume_limit('authentication-ip', request.remote_addr or 'unknown', 30, 900)
            elif g.user:
                limited = consume_limit('writes-user', str(g.user['id']), 300, 60)
            else:
                limited = None
            if limited:
                return limited
            if request.method in {'POST', 'PUT', 'PATCH'} and request.endpoint != 'logout':
                g.payload = validation.json_object()


@app.after_request
def security_headers(response):
    response.headers['Content-Language'] = 'fr'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'")
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=()'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    if app.config['SESSION_COOKIE_SECURE']:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if request.path.startswith(('/api/', '/static/')) or request.path in {'/', '/login', '/logout'}:
        response.headers['Cache-Control'] = 'no-store'
        response.vary.add('Cookie')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.endpoint:
        user = getattr(g, 'user', None)
        target_id = next(iter((request.view_args or {}).values()), None)
        if type(target_id) is not int or not 1 <= target_id <= 2147483647:
            target_id = None
        try:
            with connection() as db:
                db.execute('INSERT INTO security_events(user_id,action,target_id,status) VALUES (?,?,?,?)',
                           (user['id'] if user else None, request.endpoint, target_id, response.status_code))
                db.execute('DELETE FROM security_events WHERE id < (SELECT MAX(id)-20000 FROM security_events)')
        except sqlite3.Error:
            app.logger.error('Unable to record a security event.')
    return response


@app.errorhandler(HTTPException)
def http_error(error):
    messages = {400:'Invalid request.', 404:'Not found.', 405:'Method not allowed.',
                413:'Request is too large.', 415:'Use a JSON object with application/json.'}
    return invalid(messages.get(error.code, 'Request rejected.'), error.code)


@app.errorhandler(ValueError)
def validation_error(error):
    return invalid(str(error))


@app.errorhandler(sqlite3.IntegrityError)
def database_conflict(error):
    return invalid('Invalid or duplicate record.', 409)


@app.errorhandler(sqlite3.OperationalError)
def database_unavailable(error):
    app.logger.error('Database temporarily unavailable.')
    return invalid('Service temporarily unavailable. Try again.', 503)


@app.errorhandler(Exception)
def unexpected_error(error):
    app.logger.exception('Unexpected request failure.')
    return invalid('An unexpected server error occurred.', 500)


@app.get('/login')
def login_page():
    if g.user:
        return redirect(url_for('index'))
    return render_template('login.html', setup=setup_required(), csrf=csrf_token())


@app.get('/api/auth/session')
def auth_session():
    return jsonify(user=g.user, csrf_token=csrf_token(), setup_required=setup_required())


def credentials(payload):
    return validation.credentials(payload)


def sign_in(user, expected_hash=None):
    revoke_current_session()
    token = secrets.token_hex(32)
    now = time.time()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT password_hash,disabled FROM users WHERE id=?', (user['id'],)).fetchone()
        if not current or current['disabled'] or (expected_hash is not None and not secrets.compare_digest(current['password_hash'], expected_hash)):
            return invalid('Account credentials changed. Sign in again.', 401)
        db.execute('DELETE FROM auth_sessions WHERE expires_at<=? OR created_at<=?', (now, now - app.config['SESSION_ABSOLUTE_SECONDS']))
        db.execute('DELETE FROM auth_sessions WHERE token_hash IN (SELECT token_hash FROM auth_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT -1 OFFSET 9)', (user['id'],))
        db.execute('INSERT INTO auth_sessions VALUES (?,?,?,?,?)', (token_hash(token), user['id'], now, now, now + app.config['SESSION_IDLE_SECONDS']))
    session['auth_token'] = token
    session.permanent = True
    g.user = dict(user)
    return jsonify(user=dict(user), csrf_token=csrf_token())


@app.post('/api/auth/setup')
def setup():
    if not app.config['ALLOW_WEB_SETUP'] or request.remote_addr not in {'127.0.0.1', '::1'}:
        return invalid('First-run setup is only available locally before production hosting.', 403)
    if not setup_required():
        return invalid('Setup is complete. Ask an administrator to create your account.', 409)
    try:
        username, password = credentials(g.payload)
        password_hash = generate_password_hash(password)
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                return invalid('Setup is complete. Ask an administrator to create your account.', 409)
            cur = db.execute("INSERT INTO users(username,password_hash,role) VALUES (?,?,'admin')", (username, password_hash))
            user = {'id': cur.lastrowid, 'username': username, 'role': 'admin'}
        return sign_in(user), 201
    except (ValueError, TypeError, AttributeError) as exc:
        return invalid(str(exc))


@app.post('/api/auth/login')
def login():
    payload = g.payload
    if not isinstance(payload, dict):
        return invalid('Invalid login details.')
    username = payload.get('username', '')
    password = payload.get('password', '')
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}', username.strip()) or not isinstance(password, str) or len(password) > 128:
        return invalid('Invalid username or password.', 401)
    username = username.strip()
    identity = hmac.new(app.config['SECRET_KEY'].encode(), f'{request.remote_addr}:{username.casefold()}'.encode(), hashlib.sha256).hexdigest()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE attempted_at<?', (time.time() - 900,))
        if db.execute('SELECT COUNT(*) FROM login_attempts WHERE identity=?', (identity,)).fetchone()[0] >= 10:
            return invalid('Too many sign-in attempts. Try again in 15 minutes.', 429)
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        db.execute('INSERT INTO login_attempts VALUES (?,?)', (identity, time.time()))
    # Hash outside the write transaction; unknown users still incur the same cost.
    password_hash = user['password_hash'] if user else app.config['DUMMY_PASSWORD_HASH']
    valid = check_password_hash(password_hash, password)
    if not user or not valid or user['disabled']:
        return invalid('Invalid username or password.', 401)
    with connection() as db:
        db.execute('DELETE FROM login_attempts WHERE identity=?', (identity,))
    return sign_in({key: user[key] for key in ('id', 'username', 'role')}, user['password_hash'])


@app.post('/api/auth/logout')
def logout():
    revoke_current_session()
    return jsonify(ok=True)


@app.post('/logout')
def logout_page():
    if g.user:
        token = request.form.get('csrf_token', '')
        if not token or not secrets.compare_digest(token.encode(), session.get('csrf_token', '').encode()):
            return 'Votre session a changé. Actualisez la page, puis déconnectez-vous à nouveau.', 403
    revoke_current_session()
    return redirect(url_for('login_page'), code=303)


@app.get('/api/users')
def list_users():
    if g.user['role'] != 'admin':
        return invalid('Only administrators can manage accounts.', 403)
    with connection() as db:
        return jsonify(users=[dict(row) for row in db.execute('SELECT id,username,role,disabled,created_at FROM users ORDER BY username')])


@app.post('/api/users')
def create_user():
    try:
        payload = g.payload
        username, password = credentials(payload)
        role = validation.choice(payload.get('role', 'viewer'), {'admin', 'viewer'}, 'Rôle du compte')
        password_hash = generate_password_hash(password)
        with connection() as db:
            check_capacity(db, 'users')
            cur = db.execute('INSERT INTO users(username,password_hash,role) VALUES (?,?,?)',
                             (username, password_hash, role))
            return jsonify(id=cur.lastrowid, username=username, role=role), 201
    except sqlite3.IntegrityError:
        return invalid('That username is already in use.', 409)
    except (ValueError, TypeError, AttributeError) as exc:
        return invalid(str(exc))


@app.post('/api/auth/password')
def change_password():
    payload = g.payload
    current = payload.get('current_password')
    new_password = validation.password(payload.get('new_password'))
    if not isinstance(current, str) or len(current) > 128:
        return invalid('Current password is incorrect.', 403)
    with connection() as db:
        user = db.execute('SELECT password_hash FROM users WHERE id=?', (g.user['id'],)).fetchone()
    if not check_password_hash(user['password_hash'], current):
        return invalid('Current password is incorrect.', 403)
    new_hash = generate_password_hash(new_password)
    with connection() as db:
        cur = db.execute('UPDATE users SET password_hash=? WHERE id=? AND password_hash=?', (new_hash, g.user['id'], user['password_hash']))
        if not cur.rowcount:
            return invalid('Your password changed. Sign in again.', 409)
        db.execute('DELETE FROM auth_sessions WHERE user_id=?', (g.user['id'],))
    session.clear()
    return jsonify(ok=True)


@app.patch('/api/users/<int:uid>')
def update_user_access(uid):
    payload = g.payload
    if not payload or not set(payload).issubset({'disabled', 'role'}):
        return invalid('Provide an access role or disabled status.')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        user = db.execute('SELECT role,disabled FROM users WHERE id=?', (uid,)).fetchone()
        if not user:
            return invalid('Account not found.', 404)
        role = validation.choice(payload.get('role', user['role']), {'admin', 'viewer'}, 'Rôle')
        disabled = payload.get('disabled', bool(user['disabled']))
        if type(disabled) is not bool:
            return invalid('Disabled status must be true or false.')
        if user['role'] == 'admin' and not user['disabled'] and (disabled or role != 'admin'):
            if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0] <= 1:
                return invalid('Keep at least one active administrator.', 409)
        db.execute('UPDATE users SET role=?,disabled=? WHERE id=?', (role, int(disabled), uid))
        db.execute('DELETE FROM auth_sessions WHERE user_id=?', (uid,))
    return jsonify(ok=True)


@app.post('/api/users/<int:uid>/revoke-sessions')
def revoke_user_sessions(uid):
    with connection() as db:
        if not db.execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
            return invalid('Account not found.', 404)
        db.execute('DELETE FROM auth_sessions WHERE user_id=?', (uid,))
    return jsonify(ok=True)


@app.get('/api/security/events')
def security_events():
    if g.user['role'] != 'admin':
        return invalid('Only administrators can review security events.', 403)
    with connection() as db:
        return jsonify(events=[dict(row) for row in db.execute('SELECT * FROM security_events ORDER BY id DESC LIMIT 100')])


def check_capacity(db, entity):
    queries = {'users': ('SELECT COUNT(*) FROM users', 250), 'stages': ('SELECT COUNT(*) FROM stages', 1000),
               'teams': ('SELECT COUNT(*) FROM teams', 250), 'edges': ('SELECT COUNT(*) FROM edges', 5000),
               'macros': ('SELECT COUNT(*) FROM macro_stages', 50), 'subteams': ('SELECT COUNT(*) FROM subteams', 2000)}
    query, limit = queries[entity]
    db.execute('BEGIN IMMEDIATE')
    if db.execute(query).fetchone()[0] >= limit:
        raise ValueError('Workspace capacity reached. Contact your administrator.')


def validate_stage(payload):
    return validation.stage(payload)


def replace_teams(db, sid, team_ids):
    if team_ids:
        known = {row['id'] for row in db.execute('SELECT id FROM teams')}
        if not set(team_ids).issubset(known): raise ValueError('An assigned team does not exist.')
    db.execute('DELETE FROM stage_teams WHERE stage_id=?',(sid,))
    for tid in team_ids:
        db.execute('INSERT INTO stage_teams(stage_id,team_id) VALUES (?,?)',(sid,tid))


@app.get('/')
def index():
    if not g.user:
        return redirect(url_for('login_page'))
    return render_template('index.html', user=g.user, csrf=csrf_token())

@app.get('/api/journey')
def journey(): return jsonify(get_data())

@app.post('/api/stages')
def create_stage():
    try:
        name, desc, phase,x,y,teams = validate_stage(g.payload)
        macro_id = validation.optional_identifier(g.payload.get('macro_id'))
        with connection() as db:
            check_capacity(db, 'stages')
            cur = db.execute('INSERT INTO stages(name,description,phase,x,y,macro_id) VALUES (?,?,?,?,?,?)',(name,desc,phase,x,y,macro_id))
            replace_teams(db,cur.lastrowid,teams)
        return jsonify({'id':cur.lastrowid}),201
    except (ValueError,TypeError): return invalid('Invalid stage details.')
    except sqlite3.IntegrityError: return invalid('Invalid or duplicate stage.')

@app.put('/api/stages/<int:sid>')
def update_stage(sid):
    try:
        name,desc,phase,x,y,teams = validate_stage(g.payload)
        with connection() as db:
            existing = db.execute('SELECT macro_id FROM stages WHERE id=?',(sid,)).fetchone()
            if not existing: return invalid('Stage not found.',404)
            macro_id = validation.optional_identifier(g.payload.get('macro_id', existing['macro_id']))
            db.execute('UPDATE stages SET name=?,description=?,phase=?,x=?,y=?,macro_id=? WHERE id=?',(name,desc,phase,x,y,macro_id,sid))
            replace_teams(db,sid,teams)
        return jsonify({'ok':True})
    except (ValueError,TypeError): return invalid('Invalid stage details.')
    except sqlite3.IntegrityError: return invalid('Invalid or duplicate stage.')

@app.patch('/api/stages/<int:sid>/position')
def move_stage(sid):
    try:
        p = g.payload
        x = validation.number(p.get('x'), 'X', -10000, 10000)
        y = validation.number(p.get('y'), 'Y', -10000, 10000)
        with connection() as db:
            cur=db.execute('UPDATE stages SET x=?,y=? WHERE id=?',(x,y,sid))
            if not cur.rowcount: return invalid('Stage not found.',404)
        return jsonify({'ok':True})
    except (ValueError,TypeError,KeyError): return invalid('Invalid position.')

@app.delete('/api/stages/<int:sid>')
def delete_stage(sid):
    with connection() as db:
        cur=db.execute('DELETE FROM stages WHERE id=?',(sid,))
        if not cur.rowcount: return invalid('Stage not found.',404)
    return jsonify({'ok':True})

@app.post('/api/teams')
def create_team():
    p = g.payload
    name = validation.text(p.get('name', ''), 'Nom de l’équipe', 80, True)
    color = validation.color(p.get('color', '#38BDF8'))
    try:
        with connection() as db:
            check_capacity(db, 'teams')
            cur=db.execute('INSERT INTO teams(name,color) VALUES (?,?)',(name,color))
            tid=cur.lastrowid
        return jsonify({'id':tid}),201
    except sqlite3.IntegrityError: return invalid('This team already exists.')

@app.delete('/api/teams/<int:tid>')
def delete_team(tid):
    with connection() as db:
        cur=db.execute('DELETE FROM teams WHERE id=?',(tid,))
        if not cur.rowcount: return invalid('Team not found.',404)
    return jsonify({'ok':True})

@app.post('/api/subteams')
def create_subteam():
    team_id, name, headcount = validation.subteam(g.payload)
    with connection() as db:
        check_capacity(db, 'subteams')
        if not db.execute('SELECT 1 FROM teams WHERE id=?', (team_id,)).fetchone():
            return invalid('Équipe parente introuvable.', 404)
        if db.execute('SELECT COUNT(*) FROM subteams WHERE team_id=?', (team_id,)).fetchone()[0] >= 100:
            return invalid('Une équipe peut contenir au maximum 100 sous-équipes.')
        cur = db.execute('INSERT INTO subteams(team_id,name,headcount) VALUES (?,?,?)', (team_id,name,headcount))
        return jsonify(id=cur.lastrowid), 201


@app.put('/api/subteams/<int:subid>')
def update_subteam(subid):
    team_id, name, headcount = validation.subteam(g.payload)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT team_id FROM subteams WHERE id=?', (subid,)).fetchone()
        if not existing:
            return invalid('Sous-équipe introuvable.', 404)
        if not db.execute('SELECT 1 FROM teams WHERE id=?', (team_id,)).fetchone():
            return invalid('Équipe parente introuvable.', 404)
        if team_id != existing['team_id'] and db.execute('SELECT COUNT(*) FROM subteams WHERE team_id=?', (team_id,)).fetchone()[0] >= 100:
            return invalid('Une équipe peut contenir au maximum 100 sous-équipes.')
        db.execute('UPDATE subteams SET team_id=?,name=?,headcount=?,is_example=0 WHERE id=?', (team_id,name,headcount,subid))
    return jsonify(ok=True)


@app.delete('/api/subteams/<int:subid>')
def delete_subteam(subid):
    with connection() as db:
        if not db.execute('DELETE FROM subteams WHERE id=?', (subid,)).rowcount:
            return invalid('Sous-équipe introuvable.', 404)
    return jsonify(ok=True)


@app.post('/api/macros')
def create_macro():
    values = validation.macro(g.payload)
    with connection() as db:
        check_capacity(db, 'macros')
        cur = db.execute('INSERT INTO macro_stages(name,description,color,sort_order) VALUES (?,?,?,?)', values)
        return jsonify(id=cur.lastrowid), 201


@app.put('/api/macros/<int:mid>')
def update_macro(mid):
    values = validation.macro(g.payload)
    with connection() as db:
        if not db.execute('UPDATE macro_stages SET name=?,description=?,color=?,sort_order=? WHERE id=?', (*values,mid)).rowcount:
            return invalid('Macro-étape introuvable.', 404)
    return jsonify(ok=True)


@app.delete('/api/macros/<int:mid>')
def delete_macro(mid):
    with connection() as db:
        if not db.execute('DELETE FROM macro_stages WHERE id=?', (mid,)).rowcount:
            return invalid('Macro-étape introuvable.', 404)
    return jsonify(ok=True)


@app.post('/api/edges')
def create_edge():
    try:
        values = validate_edge(g.payload)
        with connection() as db:
            check_capacity(db, 'edges')
            cur=db.execute('INSERT INTO edges(source,target,label,shape,line_style,color,width,bend) VALUES (?,?,?,?,?,?,?,?)', values)
            eid=cur.lastrowid
        return jsonify({'id':eid}),201
    except (KeyError,ValueError,TypeError,AttributeError,sqlite3.IntegrityError): return invalid('Invalid or duplicate connection. Check the stages and line style.')


def validate_edge(payload):
    return validation.edge(payload)


@app.put('/api/edges/<int:eid>')
def update_edge(eid):
    try:
        values = validate_edge(g.payload)
        with connection() as db:
            cur = db.execute('UPDATE edges SET source=?,target=?,label=?,shape=?,line_style=?,color=?,width=?,bend=? WHERE id=?', (*values, eid))
            if not cur.rowcount:
                return invalid('Connection not found.', 404)
        return jsonify(ok=True)
    except (KeyError,ValueError,TypeError,AttributeError,sqlite3.IntegrityError):
        return invalid('Invalid or duplicate connection. Check the stages and line style.')

@app.delete('/api/edges/<int:eid>')
def delete_edge(eid):
    with connection() as db:
        cur=db.execute('DELETE FROM edges WHERE id=?',(eid,))
        if not cur.rowcount: return invalid('Connection not found.',404)
    return jsonify({'ok':True})

@app.get('/api/export')
def export_json():
    resp=jsonify(get_data());resp.headers['Content-Disposition']='attachment; filename="credit-journey.json"';return resp

app.config['DUMMY_PASSWORD_HASH'] = generate_password_hash(secrets.token_hex(32))


def ensure_port_available(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            pass
    except OSError:
        return
    raise SystemExit(f'Port {port} is already in use. Stop the running CreditFlow server before starting another copy.')


if __name__ == '__main__':
    init_db()
    if PRODUCTION and setup_required():
        raise SystemExit('Create the first administrator locally before enabling production mode.')
    port = int(os.environ.get('PORT', '5001'))
    ensure_port_available(port)
    from waitress import serve
    print(f'CreditFlow is running at http://127.0.0.1:{port} (Waitress; loopback only).', flush=True)
    serve(app, host='127.0.0.1', port=port, threads=4, connection_limit=50, channel_timeout=30,
          max_request_body_size=64 * 1024, max_request_header_size=16 * 1024,
          clear_untrusted_proxy_headers=True, expose_tracebacks=False,
          url_scheme='https' if app.config['SESSION_COOKIE_SECURE'] else 'http', ident='CreditFlow')
else:
    init_db()
    if PRODUCTION and setup_required():
        raise RuntimeError('Create the first administrator locally before production hosting.')
