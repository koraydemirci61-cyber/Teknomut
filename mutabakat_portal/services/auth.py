"""
Kullanıcı Girişi ve Oturum Servisi
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from ..database import get_connection, query_one, query_all, execute_db


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
        
        # 1. Admin (Yönetici)
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cur.fetchone():
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

        # 2. Operatör (Sadece Mutabakat Listesi & Cihaz Düzenleme)
        cur.execute("SELECT id FROM users WHERE username = 'operator'")
        if not cur.fetchone():
            cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
            """, (
                "operator",
                hash_password("operator123"),
                "Mutabakat Operatörü",
                "operator",
                "operator@teknosa.com"
            ))

        # 3. Gözetmen (Sadece Dashboard & Rapor İnceleme, Veri Giriş/Çıkışı Yok)
        cur.execute("SELECT id FROM users WHERE username = 'gozetmen'")
        if not cur.fetchone():
            cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
            """, (
                "gozetmen",
                hash_password("gozetmen123"),
                "Rapor Gözetmeni",
                "gozetmen",
                "gozetmen@teknosa.com"
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


def get_all_users() -> List[Dict[str, Any]]:
    return query_all("""
    SELECT id, username, full_name, role, email, is_active, created_at
    FROM users
    ORDER BY id ASC
    """)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    return query_one("""
    SELECT id, username, full_name, role, email, is_active, created_at
    FROM users
    WHERE id = ?
    """, (user_id,))


def create_user(
    username: str,
    password: str,
    full_name: str,
    role: str = "operator",
    email: Optional[str] = None
) -> Dict[str, Any]:
    clean_username = username.strip().lower()
    clean_full_name = full_name.strip()
    clean_email = email.strip() if email else None

    if len(clean_username) < 3:
        return {"success": False, "error": "Kullanıcı adı en az 3 karakter olmalıdır."}
    
    if len(password) < 4:
        return {"success": False, "error": "Şifre en az 4 karakter olmalıdır."}

    if not clean_full_name:
        return {"success": False, "error": "Ad ve soyad alanı boş bırakılamaz."}

    existing = query_one("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (clean_username,))
    if existing:
        return {"success": False, "error": f"'{clean_username}' kullanıcı adı zaten kullanılıyor!"}

    if role not in ("admin", "operator", "gozetmen", "reviewer"):
        role = "operator"

    pwd_hash = hash_password(password)
    user_id = execute_db("""
    INSERT INTO users (username, password_hash, full_name, role, email, is_active)
    VALUES (?, ?, ?, ?, ?, 1)
    """, (clean_username, pwd_hash, clean_full_name, role, clean_email))

    return {
        "success": True,
        "user_id": user_id,
        "message": f"'{clean_username}' kullanıcısı başarıyla oluşturuldu."
    }


def update_user_password(user_id: int, new_password: str) -> Dict[str, Any]:
    if len(new_password) < 4:
        return {"success": False, "error": "Yeni şifre en az 4 karakter olmalıdır."}

    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "error": "Kullanıcı bulunamadı."}

    pwd_hash = hash_password(new_password)
    execute_db("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
    return {
        "success": True,
        "message": f"{user['username']} kullanıcısının şifresi başarıyla güncellendi."
    }


def toggle_user_status(user_id: int, current_admin_id: int) -> Dict[str, Any]:
    if user_id == current_admin_id:
        return {"success": False, "error": "Kendi hesabınızı pasife alamazsınız!"}

    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "error": "Kullanıcı bulunamadı."}

    new_status = 0 if user["is_active"] else 1
    execute_db("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
    
    if new_status == 0:
        execute_db("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    durum_str = "aktif edildi" if new_status == 1 else "pasife alındı (giriş engellendi)"
    return {
        "success": True,
        "message": f"{user['username']} hesabı {durum_str}."
    }


def delete_user(user_id: int, current_admin_id: int) -> Dict[str, Any]:
    if user_id == current_admin_id:
        return {"success": False, "error": "Kendi yönetici hesabınızı silemezsiniz!"}

    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "error": "Kullanıcı bulunamadı."}

    if user["role"] == "admin":
        admin_count_row = query_one("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin' AND is_active = 1")
        if admin_count_row and admin_count_row["cnt"] <= 1:
            return {"success": False, "error": "Sistemdeki son aktif yönetici silinemez!"}

    execute_db("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    execute_db("DELETE FROM users WHERE id = ?", (user_id,))

    return {
        "success": True,
        "message": f"{user['username']} kullanıcısı kalıcı olarak silindi."
    }
