from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
from pathlib import Path
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from .database import connect


class PortalError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def set_admin_access(path: Path, token: str):
    if len(token) < 40:
        raise PortalError("Yönetim bağlantısı için yeterli uzunlukta rastgele anahtar gerekli.")
    with connect(path, write=True) as db:
        db.execute("UPDATE settings SET admin_access_hash=? WHERE id=1", (token_hash(token),))
        db.execute("DELETE FROM login_sessions WHERE department_id IS NULL")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_login(db: sqlite3.Connection, department_id: int | None) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM login_sessions WHERE expires_at <= ?", (time.time(),))
    db.execute(
        "INSERT INTO login_sessions VALUES (?, ?, ?, ?)",
        (token_hash(token), department_id, secrets.token_urlsafe(32), time.time() + 8 * 3600),
    )
    return token


def normalize(value: str) -> str:
    value = value.translate(str.maketrans("ıİ", "iI")).lower()
    value = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]", "", value)


def cell_text(cell) -> str:
    if cell.data_type == "f":
        raise PortalError(f"{cell.coordinate}: personel alanında formül kullanılamaz.")
    if cell.value is None:
        return ""
    if isinstance(cell.value, bool):
        raise PortalError(f"{cell.coordinate}: geçersiz hücre türü.")
    if isinstance(cell.value, (int, float)):
        if int(cell.value) != cell.value:
            raise PortalError(f"{cell.coordinate}: numara alanı tam sayı/metin olmalı.")
        value = str(int(cell.value))
        if re.fullmatch(r"0+", cell.number_format):
            value = value.zfill(len(cell.number_format))
        return value
    return str(cell.value).strip()


@dataclass(frozen=True)
class Person:
    identity_no: str
    employee_no: str
    name: str
    workplace: str
    department: str


def parse_workbook(content: bytes) -> tuple[list[Person], str]:
    aliases = {
        "tckimlikno": "identity_no", "tckimliknumarasi": "identity_no",
        "kimlikno": "identity_no", "personeladsoyad": "name",
        "adsoyad": "name", "adisoyadi": "name",
        "isyerison": "workplace", "isyeri": "workplace",
        "birimson": "department", "birim": "department", "departman": "department",
        "sicilno": "employee_no", "sicilnumarasi": "employee_no",
        "personelsicilno": "employee_no",
    }
    if len(content) > 5 * 1024 * 1024:
        raise PortalError("Excel en fazla 5 MB olabilir.")
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                raise PortalError("Excel açılmış boyutu 40 MB sınırını aşıyor.")
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
    except (BadZipFile, InvalidFileException, ParseError, KeyError, ValueError) as exc:
        if isinstance(exc, PortalError):
            raise
        raise PortalError("Geçerli bir .xlsx dosyası seçin.") from exc
    try:
        candidates = []
        required = {"identity_no", "name", "workplace", "department"}
        for sheet in workbook:
            if sheet.max_row > 10001 or sheet.max_column > 100:
                raise PortalError("Excel en fazla 10.000 personel ve 100 sütun içerebilir.")
            for row_number, row in enumerate(sheet.iter_rows(max_row=min(sheet.max_row, 20)), 1):
                columns = {}
                for index, cell in enumerate(row):
                    field = aliases.get(normalize(str(cell.value or "")))
                    if field:
                        if field in columns:
                            raise PortalError(f"{sheet.title}: yinelenen sütun başlığı.")
                        columns[field] = index
                if required <= columns.keys():
                    candidates.append((sheet, row_number, columns))
                    break
        if len(candidates) != 1:
            raise PortalError("Tek bir personel tablosu bulunmalı: T.C. Kimlik No., Personel Ad Soyad, İşyeri (Son), Birim (Son).")
        sheet, header_row, columns = candidates[0]
        people, identities = [], set()
        for row_number, row in enumerate(sheet.iter_rows(min_row=header_row + 1), header_row + 1):
            fields = {key: cell_text(row[index]) for key, index in columns.items()}
            if not any(fields.values()):
                continue
            if any(not fields[key] for key in required):
                raise PortalError(f"Satır {row_number}: zorunlu personel alanı eksik.")
            identity = fields["identity_no"]
            if not re.fullmatch(r"[0-9]{11}", identity):
                raise PortalError(f"Satır {row_number}: kimlik numarası 11 rakam olmalı.")
            if identity in identities:
                raise PortalError(f"Satır {row_number}: tekrarlanan kimlik numarası.")
            identities.add(identity)
            people.append(Person(**fields, **({} if "employee_no" in fields else {"employee_no": ""})))
        if not people:
            raise PortalError("Excel'de personel bulunamadı.")
        title = ""
        if header_row > 1:
            title = str(sheet.cell(1, 5).value or "").strip()
        return people, title
    finally:
        workbook.close()


def import_workbook(path: Path, content: bytes) -> int:
    people, title = parse_workbook(content)
    with connect(path, write=True) as db:
        # Existing assignments must not be silently reinterpreted by a new roster.
        if db.execute("SELECT COUNT(*) FROM personnel").fetchone()[0]:
            raise PortalError("Liste zaten yüklü. Mevcut seçimleri korumak için yeniden yükleme kapalı.", 409)
        for person in people:
            db.execute(
                "INSERT OR IGNORE INTO departments (name, access_token) VALUES (?, ?)",
                (person.department, secrets.token_urlsafe(32)),
            )
            department_id = db.execute(
                "SELECT id FROM departments WHERE name=?", (person.department,)
            ).fetchone()[0]
            db.execute(
                """INSERT INTO personnel
                   (id, identity_no, employee_no, name, workplace, department_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (uuid.uuid4().hex, person.identity_no, person.employee_no, person.name,
                 person.workplace, department_id),
            )
        if title:
            db.execute("UPDATE settings SET title=? WHERE id=1", (title,))
    return len(people)


def save_assignments(path: Path, department_id: int, assignments: list[dict]):
    if len({item["id"] for item in assignments}) != len(assignments):
        raise PortalError("Aynı personel bir istekte birden fazla gönderilemez.")
    for item in assignments:
        unavailable = item.get("unavailable", False)
        reason = item.get("absence_reason", "").strip()
        if unavailable and (item["session_id"] is not None or not reason):
            raise PortalError("Katılamayacak personel için seans seçmeyin ve açıklama yazın.")
        if not unavailable and reason:
            raise PortalError("Açıklama yalnız katılamayacak personel için girilebilir.")
        if len(reason) > 500:
            raise PortalError("Katılamama açıklaması en fazla 500 karakter olabilir.")
    with connect(path, write=True) as db:
        if db.execute("SELECT locked FROM settings WHERE id=1").fetchone()[0]:
            raise PortalError("Seans girişleri yönetici tarafından kapatıldı.", 403)
        for item in assignments:
            person = db.execute(
                "SELECT id, version FROM personnel WHERE id=? AND department_id=?",
                (item["id"], department_id),
            ).fetchone()
            if person is None:
                raise PortalError("Bu personel için işlem yetkiniz yok.", 403)
            if person["version"] != item["version"]:
                raise PortalError("Liste başka bir pencerede değişti. Sayfayı yenileyip tekrar deneyin.", 409)
            if item["session_id"] is not None and not db.execute(
                "SELECT 1 FROM training_sessions WHERE id=?", (item["session_id"],)
            ).fetchone():
                raise PortalError("Seçilen seans artık mevcut değil. Sayfayı yenileyin.")
        updated_at = datetime.now().isoformat(timespec="seconds")
        for item in assignments:
            db.execute(
                """UPDATE personnel SET session_id=?, unavailable=?, absence_reason=?,
                   version=version+1, updated_at=?
                   WHERE id=? AND department_id=?""",
                (item["session_id"], int(item.get("unavailable", False)),
                 item.get("absence_reason", "").strip(), updated_at, item["id"], department_id),
            )


def export_workbook(path: Path) -> io.BytesIO:
    with connect(path) as db:
        title = db.execute("SELECT title FROM settings WHERE id=1").fetchone()[0]
        rows = db.execute("""
            SELECT p.identity_no, p.employee_no, p.name, p.workplace, d.name,
                   CASE WHEN p.unavailable=1 THEN 'Katılamayacak'
                        ELSE COALESCE(s.label, 'Seçilmedi') END,
                   COALESCE(s.starts_at, ''), p.updated_at,
                   CASE WHEN p.unavailable=1 THEN 'Katılamayacak'
                        WHEN p.session_id IS NOT NULL THEN 'Katılacak' ELSE 'Seçilmedi' END,
                   p.absence_reason
            FROM personnel p JOIN departments d ON d.id=p.department_id
            LEFT JOIN training_sessions s ON s.id=p.session_id
            ORDER BY d.name, p.name, p.id
        """).fetchall()
        summary = db.execute("""
            SELECT s.label, s.starts_at, COUNT(p.id) FROM training_sessions s
            LEFT JOIN personnel p ON p.session_id=s.id GROUP BY s.id ORDER BY s.starts_at, s.id
        """).fetchall()
        unassigned = db.execute("SELECT COUNT(*) FROM personnel WHERE session_id IS NULL AND unavailable=0").fetchone()[0]
        unavailable = db.execute("SELECT COUNT(*) FROM personnel WHERE unavailable=1").fetchone()[0]
    workbook = Workbook()
    detail = workbook.active
    detail.title = "KATILIM LİSTESİ"
    detail.append(["T.C. Kimlik No.", "Sicil No.", "Personel Ad Soyad", "İşyeri", "Birim",
                   "Katılacağı Oturum", "Oturum Saati", "Son Güncelleme", "Eğitim",
                   "Katılım Durumu", "Katılamama Açıklaması"])
    for row in rows:
        detail.append([*row[:8], title, *row[8:]])
    overview = workbook.create_sheet("OTURUM ÖZETİ")
    overview.append(["Oturum", "Tarih/Saat", "Personel Sayısı"])
    for row in summary:
        overview.append(list(row))
    overview.append(["Katılamayacak", "", unavailable])
    overview.append(["Seçilmedi", "", unassigned])
    overview.append(["TOPLAM", "", len(rows)])
    for sheet in workbook:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    # Excel must keep identifiers and user-controlled values as literal text.
                    cell.data_type = "s"
                    cell.number_format = "@"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="16324F")
        for index in range(1, sheet.max_column + 1):
            sheet.column_dimensions[get_column_letter(index)].width = 26
    result = io.BytesIO()
    workbook.save(result)
    workbook.close()
    result.seek(0)
    return result
