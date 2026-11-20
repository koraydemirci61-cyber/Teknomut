from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Optional

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from .database import connect, initialize
from .services import (
    PortalError, export_workbook, import_workbook, save_assignments,
)

ROOT = Path(__file__).resolve().parent


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=32, max_length=32)
    session_id: Optional[int] = Field(default=None, ge=1)
    unavailable: bool = False
    absence_reason: str = Field(default="", max_length=500)
    version: int = Field(ge=0)


class SaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department_id: int = Field(ge=1)
    assignments: list[AssignmentInput] = Field(min_length=1, max_length=10000)


def create_app(database_path: Path) -> FastAPI:
    initialize(database_path)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database_path = database_path
    templates = Jinja2Templates(directory=str(ROOT / "templates"))
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    def render(request: Request, name: str, **context):
        return templates.TemplateResponse(request=request, name=name, context=context)

    @app.middleware("http")
    async def common_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
        })
        return response

    @app.exception_handler(PortalError)
    async def portal_error(request: Request, exc: PortalError):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": str(exc)}, status_code=exc.status)
        response = render(request, "error.html", error=str(exc))
        response.status_code = exc.status
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return await portal_error(request, PortalError("Girdi alanlarını kontrol edip tekrar deneyin.", 422))

    # --- ANA SAYFA: DEPARTMAN VE SEANS SEÇİMİ (ŞEFLER İÇİN TEK LİNK) ---
    @app.get("/")
    def index(request: Request, dept_id: Optional[int] = None):
        with connect(database_path) as db:
            settings = dict(db.execute("SELECT title, locked FROM settings WHERE id=1").fetchone())
            departments = [dict(row) for row in db.execute("""
                SELECT d.id, d.name,
                       COUNT(p.id) AS total,
                       COALESCE(SUM(CASE WHEN p.session_id IS NOT NULL THEN 1 ELSE 0 END), 0) AS assigned,
                       COALESCE(SUM(p.unavailable), 0) AS unavailable
                FROM departments d
                LEFT JOIN personnel p ON p.department_id = d.id
                GROUP BY d.id
                ORDER BY d.name
            """)]

            current_dept = None
            people = []
            if dept_id is not None:
                dept_row = db.execute("SELECT id, name FROM departments WHERE id = ?", (dept_id,)).fetchone()
                if dept_row:
                    current_dept = dict(dept_row)
                    # TC ve Sicil kesinlikle yöneticilere gönderilmez!
                    people = [dict(row) for row in db.execute("""
                        SELECT id, name, workplace, session_id, unavailable, absence_reason, version, updated_at
                        FROM personnel
                        WHERE department_id = ?
                        ORDER BY name, id
                    """, (dept_id,))]

            sessions = [dict(row) for row in db.execute("""
                SELECT id, label, starts_at FROM training_sessions ORDER BY starts_at, id
            """)]

        assigned_count = sum(1 for p in people if p["session_id"] is not None)
        unavailable_count = sum(1 for p in people if p["unavailable"])
        pending_count = len(people) - assigned_count - unavailable_count

        return render(
            request,
            "index.html",
            settings=settings,
            departments=departments,
            current_dept=current_dept,
            selected_dept_id=dept_id,
            people=people,
            sessions=sessions,
            assigned_count=assigned_count,
            unavailable_count=unavailable_count,
            pending_count=pending_count,
        )

    # --- ESKİ BAĞLANTILARI ANA SAYFAYA YÖNLENDİRME ---
    @app.get("/katilim")
    @app.get("/giris")
    @app.get("/birimler")
    def legacy_redirect():
        return RedirectResponse("/", status_code=303)

    @app.get("/birim")
    def legacy_birim(department_id: Optional[int] = None):
        if department_id:
            return RedirectResponse(f"/?dept_id={department_id}", status_code=303)
        return RedirectResponse("/", status_code=303)

    @app.get("/yonetici")
    def legacy_admin():
        return RedirectResponse("/yonetim", status_code=303)

    # --- ŞEFLERİN SEÇİMLERİNİ KAYDETME API ---
    @app.post("/api/assignments")
    def save_api(data: SaveInput):
        save_assignments(
            database_path,
            data.department_id,
            [item.model_dump() for item in data.assignments],
        )
        return {"success": True, "saved": len(data.assignments)}

    # --- YÖNETİM & RAPORLAR PANELİ (PAROLASIZ) ---
    @app.get("/yonetim")
    def admin_page(request: Request):
        with connect(database_path) as db:
            settings = dict(db.execute("SELECT title, locked FROM settings WHERE id=1").fetchone())
            departments = [dict(row) for row in db.execute("""
                SELECT d.id, d.name,
                       COUNT(p.id) AS total,
                       COALESCE(SUM(CASE WHEN p.session_id IS NOT NULL THEN 1 ELSE 0 END), 0) AS assigned,
                       COALESCE(SUM(p.unavailable), 0) AS unavailable
                FROM departments d
                LEFT JOIN personnel p ON p.department_id=d.id
                GROUP BY d.id
                ORDER BY d.name
            """)]
            sessions = [dict(row) for row in db.execute("""
                SELECT s.id, s.label, s.starts_at, COUNT(p.id) AS assigned
                FROM training_sessions s
                LEFT JOIN personnel p ON p.session_id=s.id
                GROUP BY s.id
                ORDER BY s.starts_at, s.id
            """)]

        total_personnel = sum(d["total"] for d in departments)
        total_assigned = sum(d["assigned"] for d in departments)
        total_unavailable = sum(d["unavailable"] for d in departments)
        total_pending = total_personnel - total_assigned - total_unavailable

        return render(
            request,
            "admin.html",
            settings=settings,
            departments=departments,
            sessions=sessions,
            total=total_personnel,
            assigned=total_assigned,
            unavailable=total_unavailable,
            pending=total_pending,
        )

    @app.post("/yonetim/settings")
    def settings_update(title: str = Form(min_length=1, max_length=160), locked: str = Form("")):
        if not title.strip():
            raise PortalError("Eğitim adı boş bırakılamaz.")
        with connect(database_path, write=True) as db:
            db.execute("UPDATE settings SET title=?, locked=? WHERE id=1", (title.strip(), int(locked == "on")))
        return RedirectResponse("/yonetim", status_code=303)

    @app.post("/yonetim/seans")
    def session_create(label: str = Form(min_length=1, max_length=100), starts_at: str = Form()):
        try:
            start = datetime.strptime(starts_at, "%Y-%m-%dT%H:%M")
        except ValueError as exc:
            raise PortalError("Geçerli seans tarihi ve saati girin.") from exc
        if not label.strip():
            raise PortalError("Seans adı boş bırakılamaz.")
        try:
            with connect(database_path, write=True) as db:
                db.execute(
                    "INSERT INTO training_sessions (label, starts_at) VALUES (?, ?)",
                    (label.strip(), start.isoformat(timespec="minutes")),
                )
        except sqlite3.IntegrityError as exc:
            raise PortalError("Aynı ad ve saatte seans zaten tanımlı.") from exc
        return RedirectResponse("/yonetim", status_code=303)

    @app.post("/yonetim/seans/{session_id}/sil")
    def session_delete(session_id: int):
        with connect(database_path, write=True) as db:
            if db.execute("SELECT 1 FROM personnel WHERE session_id=?", (session_id,)).fetchone():
                raise PortalError("Personele atanmış seans silinemez. Önce şefler personeli başka seansa almalıdır.", 409)
            result = db.execute("DELETE FROM training_sessions WHERE id=?", (session_id,))
            if not result.rowcount:
                raise PortalError("Seans bulunamadı.", 404)
        return RedirectResponse("/yonetim", status_code=303)

    # --- EXCEL RAPORU VE YEDEK ALMA ---
    @app.get("/yonetim/excel")
    def export():
        return StreamingResponse(
            export_workbook(database_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="destek_bilisim_isg_oturum_plani.xlsx"'},
        )

    @app.get("/yonetim/yedek")
    def backup():
        import io
        with connect(database_path) as db:
            target = sqlite3.connect(":memory:")
            try:
                db.backup(target)
                content = target.serialize()
            finally:
                target.close()
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="seans_yedek.db"'},
        )

    return app

    return app
