import base64
import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('LOAN_DB_PATH') or os.environ.get('BOOKKEEPING_DB_PATH') or (ROOT / 'data' / 'bookkeeping.db'))
BOOTSTRAP_USERNAME = os.environ.get('BOOTSTRAP_ADMIN_USERNAME', os.environ.get('ADMIN_USERNAME', 'admin')).strip() or 'admin'
BOOTSTRAP_PASSWORD_B64 = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD_B64', os.environ.get('ADMIN_PASSWORD_B64', ''))
PASSWORD_ITERATIONS = int(os.environ.get('PASSWORD_ITERATIONS', '210000'))


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def b64url_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def normalize_username(username):
    value = str(username or '').strip()
    if not value:
        raise ValueError('用户名不能为空')
    return value


def normalize_role(role):
    value = str(role or 'user').strip().lower()
    if value not in ('admin', 'user'):
        raise ValueError('角色必须是 admin 或 user')
    return value


def encode_password(password, salt=None, iterations=None):
    if isinstance(password, str):
        password = password.encode('utf-8')
    if salt is None:
        salt = os.urandom(16)
    if iterations is None:
        iterations = PASSWORD_ITERATIONS
    digest = hashlib.pbkdf2_hmac('sha256', password, salt, int(iterations))
    return f'pbkdf2_sha256${int(iterations)}${b64url(salt)}${b64url(digest)}'


def verify_password(password, stored):
    try:
        algorithm, iterations, salt_b64, digest_b64 = str(stored).split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        calc = encode_password(password, salt=b64url_decode(salt_b64), iterations=int(iterations))
        return hmac.compare_digest(calc, str(stored))
    except Exception:
        return False


def init_db():
    with connect() as db:
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(role IN ('admin','user')),
                CHECK(disabled IN (0,1))
            )
            '''
        )
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS loans (
                user_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            '''
        )
        db.commit()


def bootstrap_password():
    if not BOOTSTRAP_PASSWORD_B64:
        return None
    try:
        return base64.b64decode(BOOTSTRAP_PASSWORD_B64, validate=True).decode('utf-8')
    except Exception as exc:
        raise RuntimeError('BOOTSTRAP_ADMIN_PASSWORD_B64 必须是有效的 UTF-8 Base64') from exc


def get_user_by_id(user_id):
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (int(user_id),)).fetchone()
    return dict(row) if row else None


def get_user_by_username(username):
    name = normalize_username(username)
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (name,)).fetchone()
    return dict(row) if row else None


def list_users():
    with connect() as db:
        rows = db.execute(
            '''
            SELECT
                u.id,
                u.username,
                u.role,
                u.disabled,
                u.created_at,
                u.updated_at,
                COALESCE(l.payload, '[]') AS payload
            FROM users AS u
            LEFT JOIN loans AS l ON l.user_id = u.id
            ORDER BY u.role = 'admin' DESC, u.created_at ASC, u.id ASC
            '''
        ).fetchall()
    users = []
    for row in rows:
        try:
            payload = json.loads(row['payload'] or '[]')
            loan_count = len(payload) if isinstance(payload, list) else 0
        except Exception:
            loan_count = 0
        users.append(
            {
                'id': row['id'],
                'username': row['username'],
                'role': row['role'],
                'disabled': bool(row['disabled']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'loan_count': loan_count,
            }
        )
    return users


def count_admins():
    with connect() as db:
        row = db.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin' AND disabled=0").fetchone()
    return int(row['c'] if row else 0)


def authenticate_user(username, password):
    user = get_user_by_username(username)
    if not user or user.get('disabled'):
        return None
    if not verify_password(password, user['password_hash']):
        return None
    return user


def create_user(username, password, role='user'):
    name = normalize_username(username)
    role = normalize_role(role)
    if len(str(password or '')) < 6:
        raise ValueError('密码至少需要 6 位')
    password_hash = encode_password(password)
    with connect() as db:
        try:
            cursor = db.execute(
                'INSERT INTO users(username, password_hash, role, disabled) VALUES(?,?,?,0)',
                (name, password_hash, role),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError('用户名已存在') from exc
        user_id = cursor.lastrowid
        db.execute('INSERT OR IGNORE INTO loans(user_id, payload) VALUES(?, ?)', (user_id, '[]'))
        db.commit()
    return get_user_by_id(user_id)


def set_user_password(user_id, password):
    if len(str(password or '')) < 6:
        raise ValueError('密码至少需要 6 位')
    password_hash = encode_password(password)
    with connect() as db:
        cursor = db.execute(
            'UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (password_hash, int(user_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError('用户不存在')
        db.commit()


def set_user_disabled(user_id, disabled):
    flag = 1 if bool(disabled) else 0
    with connect() as db:
        cursor = db.execute(
            'UPDATE users SET disabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (flag, int(user_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError('用户不存在')
        db.commit()


def delete_user(user_id):
    with connect() as db:
        cursor = db.execute('DELETE FROM users WHERE id=?', (int(user_id),))
        if cursor.rowcount == 0:
            raise ValueError('用户不存在')
        db.commit()


def get_loans(user_id):
    with connect() as db:
        row = db.execute('SELECT payload FROM loans WHERE user_id=?', (int(user_id),)).fetchone()
    if not row:
        return []
    try:
        payload = json.loads(row['payload'] or '[]')
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def set_loans(user_id, loans):
    if not isinstance(loans, list):
        raise ValueError('payload must be an array')
    payload = json.dumps(loans, ensure_ascii=False, separators=(',', ':'))
    with connect() as db:
        db.execute(
            '''
            INSERT INTO loans(user_id, payload, updated_at)
            VALUES(?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP
            ''',
            (int(user_id), payload),
        )
        db.commit()


def legacy_payload():
    with connect() as db:
        row = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_state'").fetchone()
        if not row:
            return None
        legacy = db.execute('SELECT payload FROM app_state WHERE id=1').fetchone()
    if not legacy:
        return None
    try:
        payload = json.loads(legacy['payload'] or '[]')
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def migrate_legacy_payload(user_id):
    payload = legacy_payload()
    if not payload:
        return False
    if get_loans(user_id):
        return False
    set_loans(user_id, payload)
    return True


def ensure_bootstrap_admin():
    init_db()
    username = BOOTSTRAP_USERNAME
    password = bootstrap_password()

    with connect() as db:
        existing = db.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        active_admins = db.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin' AND disabled=0").fetchone()
        active_admins = int(active_admins['c'] if active_admins else 0)
        if password is None:
            if active_admins == 0:
                raise RuntimeError('缺少 BOOTSTRAP_ADMIN_PASSWORD_B64，无法创建初始管理员')
            return None
        if existing:
            if existing['role'] != 'admin' or existing['disabled'] or not verify_password(password, existing['password_hash']):
                db.execute(
                    '''
                    UPDATE users
                    SET password_hash=?, role='admin', disabled=0, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    ''',
                    (encode_password(password), existing['id']),
                )
                db.commit()
            db.execute('INSERT OR IGNORE INTO loans(user_id, payload) VALUES(?, ?)', (existing['id'], '[]'))
            db.commit()
            return get_user_by_id(existing['id'])
        if active_admins > 0:
            return None
        cursor = db.execute(
            'INSERT INTO users(username, password_hash, role, disabled) VALUES(?,?,\'admin\',0)',
            (username, encode_password(password)),
        )
        user_id = cursor.lastrowid
        db.execute('INSERT OR IGNORE INTO loans(user_id, payload) VALUES(?, ?)', (user_id, '[]'))
        db.commit()
    return get_user_by_id(user_id)
