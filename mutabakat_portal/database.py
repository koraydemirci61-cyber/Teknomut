"""
Teknosa Mutabakat Veritabanı Modülü
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "teknosa_mutabakat.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL") # Fast concurrent reads/writes
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Kullanıcılar
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'operator', -- admin, operator, reviewer
        email TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Oturumlar
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at DATETIME NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Mutabakat Kayıtları
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mutabakat_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT,
        tc_no TEXT,
        phone TEXT,
        address TEXT,
        email TEXT,
        product_id TEXT,
        imei TEXT,
        is_duplicate INTEGER DEFAULT 0,
        wega_record TEXT,
        product_no TEXT,
        brand TEXT,
        model TEXT,
        status TEXT,
        delivery_info TEXT,
        delivery_date TEXT,
        tracking_no TEXT,
        delivery_user TEXT,
        cancel_reason TEXT,
        voucher_no TEXT,
        voucher_prefix TEXT,
        voucher_amount REAL DEFAULT 0,
        voucher_status TEXT,
        start_date TEXT,
        end_date TEXT,
        order_no TEXT,
        order_amount REAL DEFAULT 0,
        order_date TEXT,
        process_start_date TEXT,
        process_user TEXT,
        store_id TEXT,
        store_name TEXT,
        company_name TEXT,
        sent TEXT,
        q1_working TEXT,
        q2_btk TEXT,
        q3_home_faceid TEXT,
        q4_icloud TEXT,
        q5_apple_body TEXT,
        q6_apple_screen TEXT,
        q7_apple_camera TEXT,
        q8_apple_battery TEXT,
        q5_android_camera TEXT,
        q6_android_body TEXT,
        q7_android_screen TEXT,
        calculated_price REAL DEFAULT 0,
        penalty_points REAL DEFAULT 0,
        full_price REAL DEFAULT 0,
        difference_amount REAL DEFAULT 0,
        reconciliation_status TEXT DEFAULT 'Cevap bekleniyor',
        screen_original TEXT,
        camera_original TEXT,
        battery_original TEXT,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_imei ON mutabakat_records(imei);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_store ON mutabakat_records(store_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_status ON mutabakat_records(reconciliation_status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_customer ON mutabakat_records(customer_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_brand ON mutabakat_records(brand);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_model ON mutabakat_records(model);")

    conn.commit()
    conn.close()


def query_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def query_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute_db(query: str, params: tuple = ()) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
