"""
Kullanıcı Girişi ve Oturum Servisi
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from ..database import get_connection, query_one, execute_db


def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"{salt}${hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split("$", 1)
        expected = hash_password(password, salt)
        return secrets.compare_digest(expected, stored_hash)
    except Exception:
        return False


def seed_default_users():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM users")
        count = cur.fetchone()["count"]
        if count == 0:
            cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
            """, (
                "admin",
                hash_password("admin123"),
                "Sistem Yöneticisi",
                "admin",
                "admin@teknosa.com"
            ))
            cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
            """, (
                "operator",
                hash_password("operator123"),
                "Mutabakat Operatörü",
                "operator",
                "mutabakat@teknosa.com"
            ))
            conn.commit()
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = query_one("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
    if not user:
        return None
    if verify_password(password, user["password_hash"]):
        return user
    return None


def create_session(user_id: int, days_valid: int = 7) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_valid)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO sessions (token, user_id, expires_at)
        VALUES (?, ?, ?)
        """, (token, user_id, expires_at.isoformat()))
        conn.commit()
    finally:
        conn.close()
    return token


def get_current_user_from_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    now_iso = datetime.now(timezone.utc).isoformat()
    query = """
    SELECT u.id, u.username, u.full_name, u.role, u.email
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
    """
    return query_one(query, (token, now_iso))


def remove_session(token: str):
    execute_db("DELETE FROM sessions WHERE token = ?", (token,))
