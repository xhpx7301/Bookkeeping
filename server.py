import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from bookkeeping_store import (
    authenticate_user,
    count_admins,
    ensure_bootstrap_admin,
    get_loans,
    get_user_by_id,
    init_db,
    list_users,
    migrate_legacy_payload,
    set_loans,
    set_user_disabled,
    set_user_password,
    delete_user,
    create_user,
)

ROOT = Path(__file__).resolve().parent
WEB_FILE = ROOT / 'loan-ledger.html'
SESSION_SECRET = os.environ.get('SESSION_SECRET', '')
SESSION_TTL = int(os.environ.get('SESSION_TTL', '604800'))
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() not in ('0', 'false', 'no')
COOKIE_NAME = 'bookkeeping_session'
MAX_BODY = 5 * 1024 * 1024

if len(SESSION_SECRET) < 32:
    raise SystemExit('SESSION_SECRET 缺失或太短。请先运行 bk settings。')


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def issue_session(user):
    payload = json.dumps(
        {'uid': int(user['id']), 'exp': int(time.time()) + SESSION_TTL, 'n': secrets.token_hex(8)},
        separators=(',', ':'),
    ).encode('utf-8')
    encoded = b64url(payload)
    signature = hmac.new(SESSION_SECRET.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha256).digest()
    return encoded + '.' + b64url(signature)


def decode_session(token):
    encoded, supplied = token.split('.', 1)
    expected = b64url(hmac.new(SESSION_SECRET.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha256).digest())
    if not hmac.compare_digest(supplied, expected):
        return None
    padding = '=' * (-len(encoded) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
    if int(payload.get('exp', 0)) <= int(time.time()):
        return None
    user = get_user_by_id(payload.get('uid'))
    if not user or user.get('disabled'):
        return None
    return user


class Handler(BaseHTTPRequestHandler):
    def route_path(self):
        return urlsplit(self.path).path

    def send_json(self, code, value, extra_headers=None):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, val in (extra_headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self):
        raw = WEB_FILE.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(raw)

    def body_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > MAX_BODY:
            raise ValueError('请求体为空或过大')
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def session_token(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            return jar[COOKIE_NAME].value if COOKIE_NAME in jar else ''
        except cookies.CookieError:
            return ''

    def current_user(self):
        token = self.session_token()
        if not token:
            return None
        try:
            return decode_session(token)
        except Exception:
            return None

    def require_auth(self):
        user = self.current_user()
        if user:
            return user
        self.send_json(401, {'ok': False, 'error': 'unauthorized'})
        return None

    def require_admin(self):
        user = self.require_auth()
        if not user:
            return None
        if user.get('role') != 'admin':
            self.send_json(403, {'ok': False, 'error': 'forbidden'})
            return None
        return user

    def cookie_header(self, token='', max_age=None):
        parts = [f'{COOKIE_NAME}={token}', 'Path=/', 'HttpOnly', 'SameSite=Lax']
        if COOKIE_SECURE:
            parts.append('Secure')
        if max_age is not None:
            parts.extend([f'Max-Age={max_age}', 'Expires=Thu, 01 Jan 1970 00:00:00 GMT'])
        return '; '.join(parts)

    def auth_payload(self, user):
        return {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'disabled': bool(user['disabled']),
        }

    def do_GET(self):
        path = self.route_path()
        if path == '/api/health':
            self.send_json(200, {'ok': True})
        elif path == '/api/auth/status':
            user = self.current_user()
            self.send_json(200, {'authenticated': bool(user), 'user': self.auth_payload(user) if user else None})
        elif path == '/api/loans':
            user = self.require_auth()
            if user:
                self.send_json(200, get_loans(user['id']))
        elif path == '/api/admin/users':
            user = self.require_admin()
            if user:
                self.send_json(200, {'users': list_users()})
        elif path in ('/', '/loan-ledger.html'):
            self.send_html()
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.route_path()
        if path == '/api/auth/login':
            try:
                value = self.body_json()
                username = str(value.get('username', ''))
                password = str(value.get('password', ''))
                user = authenticate_user(username, password)
                if not user:
                    time.sleep(0.35)
                    self.send_json(401, {'ok': False, 'error': '用户名或密码错误'})
                    return
                token = issue_session(user)
                self.send_json(200, {'ok': True, 'user': self.auth_payload(user)}, {'Set-Cookie': self.cookie_header(token)})
            except (ValueError, json.JSONDecodeError):
                self.send_json(400, {'ok': False, 'error': '请求格式不正确'})
        elif path == '/api/auth/logout':
            self.send_json(200, {'ok': True}, {'Set-Cookie': self.cookie_header('', 0)})
        elif path == '/api/loans':
            user = self.require_auth()
            if not user:
                return
            try:
                value = self.body_json()
                if not isinstance(value, list):
                    raise ValueError('payload must be an array')
                set_loans(user['id'], value)
                self.send_json(200, {'ok': True, 'count': len(value)})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json(400, {'ok': False, 'error': str(exc)})
        elif path == '/api/admin/users':
            user = self.require_admin()
            if not user:
                return
            try:
                value = self.body_json()
                created = create_user(value.get('username', ''), value.get('password', ''), value.get('role', 'user'))
                self.send_json(200, {'ok': True, 'user': self.auth_payload(created)})
            except ValueError as exc:
                self.send_json(400, {'ok': False, 'error': str(exc)})
        elif path.startswith('/api/admin/users/') and path.endswith('/password'):
            admin = self.require_admin()
            if not admin:
                return
            try:
                user_id = int(path.split('/')[4])
                target = get_user_by_id(user_id)
                if not target:
                    self.send_json(404, {'ok': False, 'error': '用户不存在'})
                    return
                value = self.body_json()
                set_user_password(user_id, value.get('password', ''))
                self.send_json(200, {'ok': True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json(400, {'ok': False, 'error': str(exc)})
        elif path.startswith('/api/admin/users/') and path.endswith('/status'):
            admin = self.require_admin()
            if not admin:
                return
            try:
                user_id = int(path.split('/')[4])
                target = get_user_by_id(user_id)
                if not target:
                    self.send_json(404, {'ok': False, 'error': '用户不存在'})
                    return
                if target['id'] == admin['id']:
                    self.send_json(400, {'ok': False, 'error': '不能修改当前登录账号状态'})
                    return
                value = self.body_json()
                disabled = bool(value.get('disabled'))
                if target['role'] == 'admin' and disabled and count_admins() <= 1:
                    self.send_json(400, {'ok': False, 'error': '至少保留一个管理员'})
                    return
                set_user_disabled(user_id, disabled)
                self.send_json(200, {'ok': True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json(400, {'ok': False, 'error': str(exc)})
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = self.route_path()
        if path.startswith('/api/admin/users/'):
            admin = self.require_admin()
            if not admin:
                return
            try:
                user_id = int(path.split('/')[4])
                target = get_user_by_id(user_id)
                if not target:
                    self.send_json(404, {'ok': False, 'error': '用户不存在'})
                    return
                if target['id'] == admin['id']:
                    self.send_json(400, {'ok': False, 'error': '不能删除当前登录账号'})
                    return
                if target['role'] == 'admin' and count_admins() <= 1:
                    self.send_json(400, {'ok': False, 'error': '至少保留一个管理员'})
                    return
                delete_user(user_id)
                self.send_json(200, {'ok': True})
            except ValueError as exc:
                self.send_json(400, {'ok': False, 'error': str(exc)})
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt % args))


if __name__ == '__main__':
    init_db()
    bootstrap_admin = ensure_bootstrap_admin()
    if bootstrap_admin:
        migrate_legacy_payload(bootstrap_admin['id'])
    port = int(os.environ.get('PORT', '8080'))
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
