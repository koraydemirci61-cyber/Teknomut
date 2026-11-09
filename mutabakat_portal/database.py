"""
Teknosa Mutabakat Veritabanı Modülü
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "teknosa_mutabakat.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL") # Fast concurrent reads/writes
    conn.execute("PRAGMA synchronous = NORMAL") # High throughput concurrent writes
    conn.execute("PRAGMA busy_timeout = 30000") # 30s busy timeout for concurrent transactions
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
        import_batch_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # İçe Aktarma Paketleri (Geri alma ve geçmiş takibi için)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT UNIQUE NOT NULL,
        filename TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        total_rows INTEGER DEFAULT 0,
        imported_count INTEGER DEFAULT 0,
        skipped_count INTEGER DEFAULT 0,
        updated_count INTEGER DEFAULT 0,
        total_voucher REAL DEFAULT 0,
        imported_by TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', -- active, reverted
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        reverted_at DATETIME
    );
    """)

    # Hasar & Fonksiyon Soru Maddeleri (Yönetici tarafından dinamik düzenlenebilir)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inspection_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        device_group TEXT NOT NULL DEFAULT 'ALL', -- ALL, APPLE, ANDROID
        question_type TEXT NOT NULL DEFAULT 'multi', -- bool, multi
        options_json TEXT NOT NULL,
        order_num INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Varsayılan soru maddelerini ekle (eğer tablo boşsa)
    cur.execute("SELECT COUNT(*) as count FROM inspection_questions")
    if cur.fetchone()["count"] == 0:
        import json
        defaults = [
            ("q1_working", "1. Cihaz çalışır durumdadır ve bataryası mevcuttur", "ALL", "bool", json.dumps([
                {"val": "", "label": "Sorun Yok / Çalışıyor", "penalty": 0},
                {"val": "Y", "label": "Çalışmıyor / Batarya Yok", "penalty": 100}
            ], ensure_ascii=False), 1),
            ("q2_btk", "2. Cihazın BTK sorgusu temizdir (Çalıntı, klon veya pasaport kayıtlı DEĞİL)", "ALL", "bool", json.dumps([
                {"val": "", "label": "Temiz / Sorun Yok", "penalty": 0},
                {"val": "Y", "label": "Sorunlu / Klon / Çalıntı", "penalty": 100}
            ], ensure_ascii=False), 2),
            ("q3_home_faceid", "3. Home tuşu, Parmak İzi veya Face ID çalışıyor mu?", "ALL", "bool", json.dumps([
                {"val": "", "label": "Çalışıyor", "penalty": 0},
                {"val": "Y", "label": "Çalışmıyor / Arızalı", "penalty": 40}
            ], ensure_ascii=False), 3),
            ("q4_icloud", "4. Cihaz sıfırlandı, iCloud / Google hesap kaldırıldı", "ALL", "bool", json.dumps([
                {"val": "", "label": "Sıfırlandı / Kilit Açık", "penalty": 0},
                {"val": "Y", "label": "Kilitli / Hesap Kaldırılmadı", "penalty": 70}
            ], ensure_ascii=False), 4),
            ("q5_apple_body", "5. (Apple) Kasa Durumu", "APPLE", "multi", json.dumps([
                {"val": "", "label": "Temiz / Hasarsız", "penalty": 0},
                {"val": "D", "label": "Çizik / Boya Soyulması", "penalty": 10},
                {"val": "Y", "label": "Çatlak / Kırık / Kasa Açık", "penalty": 15}
            ], ensure_ascii=False), 5),
            ("q6_apple_screen", "6. (Apple) Ekran Durumu", "APPLE", "multi", json.dumps([
                {"val": "", "label": "Kusursuz", "penalty": 0},
                {"val": "D", "label": "Çizik", "penalty": 15},
                {"val": "Y", "label": "Kırık / Leke / Sararma / Yanma / Bilinmeyen Parça", "penalty": 40}
            ], ensure_ascii=False), 6),
            ("q7_apple_camera", "7. (Apple) Kamera Durumu", "APPLE", "multi", json.dumps([
                {"val": "", "label": "Temiz", "penalty": 0},
                {"val": "D", "label": "Leke / Renk Değişimi", "penalty": 15},
                {"val": "Y", "label": "Bilinmeyen Parça / Arızalı", "penalty": 25}
            ], ensure_ascii=False), 7),
            ("q8_apple_battery", "8. (Apple) Pil Durumu", "APPLE", "multi", json.dumps([
                {"val": "", "label": "Sağlıklı (Pil >= %85)", "penalty": 0},
                {"val": "D", "label": "Pil Sağlığı %85 Altında", "penalty": 15},
                {"val": "Y", "label": "Bilinmeyen Parça / Şişik", "penalty": 25}
            ], ensure_ascii=False), 8),
            ("q5_android_camera", "5. (Android) Kamera Durumu", "ANDROID", "bool", json.dumps([
                {"val": "", "label": "Leke / Kusur Yok", "penalty": 0},
                {"val": "Y", "label": "Görüntüde Leke / Renk Değişimi Var", "penalty": 40}
            ], ensure_ascii=False), 9),
            ("q6_android_body", "6. (Android) Kasa Durumu", "ANDROID", "multi", json.dumps([
                {"val": "", "label": "Temiz", "penalty": 0},
                {"val": "D", "label": "Çizik / Boya Soyulması", "penalty": 15},
                {"val": "Y", "label": "Çatlak / Kırık / Kasa Açık", "penalty": 20}
            ], ensure_ascii=False), 10),
            ("q7_android_screen", "7. (Android) Ekran Durumu", "ANDROID", "multi", json.dumps([
                {"val": "", "label": "Kusursuz", "penalty": 0},
                {"val": "D", "label": "Çizik", "penalty": 20},
                {"val": "Y", "label": "Kırık / Leke / Sararma / Hayalet Ekran", "penalty": 40}
            ], ensure_ascii=False), 11),
        ]
        cur.executemany("""
        INSERT INTO inspection_questions (code, title, device_group, question_type, options_json, order_num)
        VALUES (?, ?, ?, ?, ?, ?)
        """, defaults)

    # Mevcut tabloya gerekirse sütun ekle
    cur.execute("PRAGMA table_info(mutabakat_records)")
    existing_cols = [r["name"] for r in cur.fetchall()]
    if "import_batch_id" not in existing_cols:
        cur.execute("ALTER TABLE mutabakat_records ADD COLUMN import_batch_id TEXT;")
    if "updated_at" not in existing_cols:
        cur.execute("ALTER TABLE mutabakat_records ADD COLUMN updated_at DATETIME;")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_imei ON mutabakat_records(imei);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_store ON mutabakat_records(store_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_status ON mutabakat_records(reconciliation_status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_customer ON mutabakat_records(customer_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_brand ON mutabakat_records(brand);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_model ON mutabakat_records(model);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_process_user ON mutabakat_records(process_user);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_process_date ON mutabakat_records(process_start_date);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_import_batch ON mutabakat_records(import_batch_id);")

    # IMEI'si silinen / boş olan satırları veritabanından anında kalıcı olarak temizleme tetikleyicileri
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_purge_empty_imei_insert AFTER INSERT ON mutabakat_records
    WHEN NEW.imei IS NULL OR TRIM(NEW.imei) = '' OR LENGTH(TRIM(NEW.imei)) < 8
    BEGIN
        DELETE FROM mutabakat_records WHERE id = NEW.id;
    END;
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_purge_empty_imei_update AFTER UPDATE ON mutabakat_records
    WHEN NEW.imei IS NULL OR TRIM(NEW.imei) = '' OR LENGTH(TRIM(NEW.imei)) < 8
    BEGIN
        DELETE FROM mutabakat_records WHERE id = NEW.id;
    END;
    """)

    # Başlangıçta olası boş/silinmiş IMEI kayıtlarını temizle
    cur.execute("DELETE FROM mutabakat_records WHERE imei IS NULL OR TRIM(imei) = '' OR LENGTH(TRIM(imei)) < 8 OR imei = '0' OR imei = '-';")

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
