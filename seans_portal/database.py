from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def connect(path: Path, *, write: bool = False):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


DEFAULT_TITLE = "Destek Bilişim İş Sağlığı ve Güvenliği Eğitimi Oturum Planı"
DEFAULT_SESSIONS = [
    ("1. Oturum (09:30 - 10:30)", "2026-11-19T09:30"),
    ("2. Oturum (10:45 - 11:45)", "2026-11-19T10:45"),
    ("3. Oturum (13:30 - 14:30)", "2026-11-19T13:30"),
    ("4. Oturum (14:45 - 15:45)", "2026-11-19T14:45"),
]


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(f"""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id=1),
                title TEXT NOT NULL DEFAULT '{DEFAULT_TITLE}',
                locked INTEGER NOT NULL DEFAULT 0,
                admin_access_hash TEXT NOT NULL DEFAULT ''
            );
            INSERT OR IGNORE INTO settings (id, title) VALUES (1, '{DEFAULT_TITLE}');
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                access_token TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS training_sessions (
                id INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                UNIQUE(label, starts_at)
            );
            CREATE TABLE IF NOT EXISTS personnel (
                id TEXT PRIMARY KEY,
                identity_no TEXT NOT NULL UNIQUE,
                employee_no TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL,
                workplace TEXT NOT NULL,
                department_id INTEGER NOT NULL REFERENCES departments(id),
                session_id INTEGER REFERENCES training_sessions(id),
                unavailable INTEGER NOT NULL DEFAULT 0 CHECK (unavailable IN (0, 1)),
                absence_reason TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS personnel_department ON personnel(department_id);
            CREATE TABLE IF NOT EXISTS login_sessions (
                token_hash TEXT PRIMARY KEY,
                department_id INTEGER REFERENCES departments(id),
                csrf TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
        """)
        settings_columns = {row[1] for row in db.execute("PRAGMA table_info(settings)")}
        if "admin_access_hash" not in settings_columns:
            db.execute("ALTER TABLE settings ADD COLUMN admin_access_hash TEXT NOT NULL DEFAULT ''")
        if "password_hash" in settings_columns:
            db.execute("ALTER TABLE settings DROP COLUMN password_hash")
            db.execute("DELETE FROM login_sessions WHERE department_id IS NULL")
        db.execute("DROP TABLE IF EXISTS login_attempts")
        columns = {row[1] for row in db.execute("PRAGMA table_info(personnel)")}
        if "unavailable" not in columns:
            db.execute("ALTER TABLE personnel ADD COLUMN unavailable INTEGER NOT NULL DEFAULT 0 CHECK (unavailable IN (0, 1))")
        if "absence_reason" not in columns:
            db.execute("ALTER TABLE personnel ADD COLUMN absence_reason TEXT NOT NULL DEFAULT ''")

        # Oturumlar boşsa veya atama yokken eski oturumlar varsa 4 resmi oturumu yükle
        assigned_count = db.execute("SELECT COUNT(*) FROM personnel WHERE session_id IS NOT NULL").fetchone()[0]
        if assigned_count == 0:
            db.execute("DELETE FROM training_sessions")
            for label, starts_at in DEFAULT_SESSIONS:
                db.execute(
                    "INSERT OR IGNORE INTO training_sessions (label, starts_at) VALUES (?, ?)",
                    (label, starts_at),
                )
            db.execute("UPDATE settings SET title=? WHERE id=1", (DEFAULT_TITLE,))

        db.commit()
