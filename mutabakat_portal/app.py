"""
Teknosa Mutabakat ve Hakediş Yönetim Portalı — FastAPI Ana Web Uygulaması
"""
from fastapi import FastAPI, Request, Response, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import date
from typing import Optional, Dict, Any, List
import math

from .database import init_db, query_all, query_one, execute_db
from .services.auth import (
    seed_default_users,
    authenticate_user,
    create_session,
    get_current_user_from_token,
    remove_session,
    hash_password
)
from .services.calculator import (
    QUESTIONS_DEF,
    calculate_penalty_points,
    calculate_valuation
)
from .services.exporter import generate_mutabakat_excel
from .services.daily_importer import import_daily_excel

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Teknosa Mutabakat Portalı", version="1.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup():
    init_db()
    seed_default_users()
    print("Teknosa Mutabakat Portalı Başlatıldı.")


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get("session_token")
    return get_current_user_from_token(token)


# ----------------------------------------------------
# OTURUM AÇMA / KAPATMA ROTLARI
# ----------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: Optional[str] = None):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="login.html", context={
        "error": error,
        "current_user": None
    })


@app.post("/login")
def login_action(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    user = authenticate_user(username.strip(), password)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={
            "error": "Kullanıcı adı veya şifre hatalı!",
            "current_user": None
        }, status_code=400)

    token = create_session(user["id"])
    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax"
    )
    return redirect


@app.get("/logout")
def logout_action(request: Request):
    token = request.cookies.get("session_token")
    if token:
        remove_session(token)
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie("session_token")
    return redirect


# ----------------------------------------------------
# DASHBOARD
# ----------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    # İstatistikler
    stats_raw = query_one("""
    SELECT 
        COUNT(*) as total,
        COALESCE(SUM(voucher_amount), 0) as total_voucher,
        COALESCE(SUM(calculated_price), 0) as total_calculated,
        COALESCE(SUM(difference_amount), 0) as total_diff
    FROM mutabakat_records
    """)

    status_counts = query_all("""
    SELECT reconciliation_status, COUNT(*) as c 
    FROM mutabakat_records 
    GROUP BY reconciliation_status 
    ORDER BY c DESC
    """)

    brand_counts = query_all("""
    SELECT brand, COUNT(*) as c 
    FROM mutabakat_records 
    WHERE brand != '' 
    GROUP BY brand 
    ORDER BY c DESC 
    LIMIT 6
    """)

    # Tamamlanma oranı
    completed_count = sum(s["c"] for s in status_counts if s["reconciliation_status"] == "Mutabakat tamamlandı")
    total_count = stats_raw["total"] or 0
    completed_pct = round((completed_count / total_count * 100), 1) if total_count > 0 else 0

    stats = {
        "total": total_count,
        "total_voucher": stats_raw["total_voucher"] or 0,
        "total_calculated": stats_raw["total_calculated"] or 0,
        "total_diff": stats_raw["total_diff"] or 0,
        "completed_count": completed_count,
        "completed_pct": completed_pct,
        "status_counts": status_counts,
        "brand_counts": brand_counts
    }

    # En yüksek fark çıkan 8 işlem
    top_diff_records = query_all("""
    SELECT id, imei, customer_name, brand, model, store_name, voucher_amount, calculated_price, difference_amount, reconciliation_status
    FROM mutabakat_records
    WHERE difference_amount != 0
    ORDER BY ABS(difference_amount) DESC
    LIMIT 8
    """)

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "current_user": user,
        "active_page": "dashboard",
        "stats": stats,
        "top_diff_records": top_diff_records
    })


# ----------------------------------------------------
# MUTABAKAT LİSTESİ
# ----------------------------------------------------

@app.get("/mutabakat", response_class=HTMLResponse)
def mutabakat_list_view(
    request: Request,
    page: int = 1,
    q: str = "",
    status: str = "",
    diff: str = "",
    msg: Optional[str] = None
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    page_size = 50
    offset = max(0, (page - 1) * page_size)

    where_clauses = ["1=1"]
    params = []

    if q.strip():
        search_term = f"%{q.strip()}%"
        where_clauses.append("(imei LIKE ? OR customer_name LIKE ? OR store_name LIKE ? OR model LIKE ?)")
        params.extend([search_term, search_term, search_term, search_term])

    if status.strip():
        where_clauses.append("reconciliation_status = ?")
        params.append(status.strip())

    if diff == "has_diff":
        where_clauses.append("difference_amount != 0")
    elif diff == "negative":
        where_clauses.append("difference_amount < 0")
    elif diff == "positive":
        where_clauses.append("difference_amount > 0")
    elif diff == "zero":
        where_clauses.append("difference_amount = 0")

    where_sql = " AND ".join(where_clauses)

    count_res = query_one(f"SELECT COUNT(*) as c FROM mutabakat_records WHERE {where_sql}", tuple(params))
    total_count = count_res["c"] if count_res else 0
    total_pages = max(1, math.ceil(total_count / page_size))

    records = query_all(f"""
    SELECT id, imei, is_duplicate, customer_name, phone, tc_no, store_name,
           brand, model, voucher_amount, penalty_points, calculated_price, difference_amount,
           reconciliation_status, process_start_date, delivery_date
    FROM mutabakat_records
    WHERE {where_sql}
    ORDER BY id DESC
    LIMIT ? OFFSET ?
    """, tuple(params + [page_size, offset]))

    return templates.TemplateResponse(request=request, name="mutabakat_list.html", context={
        "current_user": user,
        "active_page": "mutabakat",
        "records": records,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "q": q,
        "status_filter": status,
        "diff_filter": diff,
        "message": msg
    })


# ----------------------------------------------------
# YENİ CİHAZ GİRİŞİ (KULLANICI GİRİŞİ)
# ----------------------------------------------------

@app.get("/mutabakat/new", response_class=HTMLResponse)
def new_mutabakat_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    models = query_all("SELECT model_name, full_price FROM model_prices ORDER BY model_name ASC")

    return templates.TemplateResponse(request=request, name="mutabakat_form.html", context={
        "current_user": user,
        "active_page": "new",
        "is_edit": False,
        "record": {},
        "questions": QUESTIONS_DEF,
        "model_list": models,
        "today_str": date.today().strftime("%Y-%m-%d")
    })


@app.post("/mutabakat/new")
def create_mutabakat_action(
    request: Request,
    customer_name: str = Form(...),
    tc_no: str = Form(""),
    phone: str = Form(""),
    store_name: str = Form(...),
    process_user: str = Form(""),
    process_start_date: str = Form(""),
    imei: str = Form(...),
    brand: str = Form(...),
    model: str = Form(...),
    full_price: float = Form(0.0),
    voucher_amount: float = Form(0.0),
    voucher_no: str = Form(""),
    reconciliation_status: str = Form("Cevap bekleniyor"),
    screen_original: str = Form(""),
    camera_original: str = Form(""),
    battery_original: str = Form(""),
    notes: str = Form(""),
    # Sorular:
    q1_working: str = Form(""),
    q2_btk: str = Form(""),
    q3_home_faceid: str = Form(""),
    q4_icloud: str = Form(""),
    q5_apple_body: str = Form(""),
    q6_apple_screen: str = Form(""),
    q7_apple_camera: str = Form(""),
    q8_apple_battery: str = Form(""),
    q5_android_camera: str = Form(""),
    q6_android_body: str = Form(""),
    q7_android_screen: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    clean_imei = imei.strip()
    
    # Çift IMEI Kontrolü
    existing_imei = query_one("SELECT COUNT(*) as c FROM mutabakat_records WHERE imei = ?", (clean_imei,))
    is_duplicate = 1 if (existing_imei and existing_imei["c"] > 0) else 0

    answers = {
        "q1_working": q1_working,
        "q2_btk": q2_btk,
        "q3_home_faceid": q3_home_faceid,
        "q4_icloud": q4_icloud,
        "q5_apple_body": q5_apple_body,
        "q6_apple_screen": q6_apple_screen,
        "q7_apple_camera": q7_apple_camera,
        "q8_apple_battery": q8_apple_battery,
        "q5_android_camera": q5_android_camera,
        "q6_android_body": q6_android_body,
        "q7_android_screen": q7_android_screen
    }

    penalty = calculate_penalty_points(answers)
    calculated_price, diff_amount = calculate_valuation(full_price, penalty, voucher_amount)

    rec_id = execute_db("""
    INSERT INTO mutabakat_records (
        customer_name, tc_no, phone, store_name, process_user, process_start_date,
        imei, is_duplicate, brand, model, full_price, voucher_amount, voucher_no,
        reconciliation_status, screen_original, camera_original, battery_original, notes,
        q1_working, q2_btk, q3_home_faceid, q4_icloud,
        q5_apple_body, q6_apple_screen, q7_apple_camera, q8_apple_battery,
        q5_android_camera, q6_android_body, q7_android_screen,
        penalty_points, calculated_price, difference_amount
    ) VALUES (
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?
    )
    """, (
        customer_name.strip(), tc_no.strip(), phone.strip(), store_name.strip(),
        process_user.strip() or user["full_name"], process_start_date or date.today().strftime("%Y-%m-%d"),
        clean_imei, is_duplicate, brand.strip(), model.strip(), full_price, voucher_amount, voucher_no.strip(),
        reconciliation_status, screen_original, camera_original, battery_original, notes.strip(),
        q1_working, q2_btk, q3_home_faceid, q4_icloud,
        q5_apple_body, q6_apple_screen, q7_apple_camera, q8_apple_battery,
        q5_android_camera, q6_android_body, q7_android_screen,
        penalty, calculated_price, diff_amount
    ))

    # Daha önce girilmiş aynı IMEI'leri de çift adet olarak güncelle
    if is_duplicate:
        execute_db("UPDATE mutabakat_records SET is_duplicate = 1 WHERE imei = ?", (clean_imei,))

    return RedirectResponse(
        url=f"/mutabakat/{rec_id}?msg=Yeni+cihaz+kaydedildi+(Hakediş:+{calculated_price:,.2f}+₺)",
        status_code=status.HTTP_302_FOUND
    )


# ----------------------------------------------------
# CİHAZ MUTABAKAT DETAYI & FİŞİ
# ----------------------------------------------------

@app.get("/mutabakat/{record_id}", response_class=HTMLResponse)
def mutabakat_detail_view(request: Request, record_id: int, msg: Optional[str] = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    rec = query_one("SELECT * FROM mutabakat_records WHERE id = ?", (record_id,))
    if not rec:
        return RedirectResponse(url="/mutabakat")

    return templates.TemplateResponse(request=request, name="mutabakat_detail.html", context={
        "current_user": user,
        "active_page": "mutabakat",
        "record": rec,
        "today_str": date.today().strftime("%d.%m.%Y"),
        "message": msg
    })


# ----------------------------------------------------
# CİHAZ DÜZENLEME & YENİDEN PUANLAMA
# ----------------------------------------------------

@app.get("/mutabakat/{record_id}/edit", response_class=HTMLResponse)
def edit_mutabakat_view(request: Request, record_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    rec = query_one("SELECT * FROM mutabakat_records WHERE id = ?", (record_id,))
    if not rec:
        return RedirectResponse(url="/mutabakat")

    models = query_all("SELECT model_name, full_price FROM model_prices ORDER BY model_name ASC")

    return templates.TemplateResponse(request=request, name="mutabakat_form.html", context={
        "current_user": user,
        "active_page": "mutabakat",
        "is_edit": True,
        "record": rec,
        "questions": QUESTIONS_DEF,
        "model_list": models,
        "today_str": date.today().strftime("%Y-%m-%d")
    })


@app.post("/mutabakat/{record_id}/edit")
def update_mutabakat_action(
    request: Request,
    record_id: int,
    customer_name: str = Form(...),
    tc_no: str = Form(""),
    phone: str = Form(""),
    store_name: str = Form(...),
    process_user: str = Form(""),
    process_start_date: str = Form(""),
    imei: str = Form(...),
    brand: str = Form(...),
    model: str = Form(...),
    full_price: float = Form(0.0),
    voucher_amount: float = Form(0.0),
    voucher_no: str = Form(""),
    reconciliation_status: str = Form("Cevap bekleniyor"),
    screen_original: str = Form(""),
    camera_original: str = Form(""),
    battery_original: str = Form(""),
    notes: str = Form(""),
    # Sorular:
    q1_working: str = Form(""),
    q2_btk: str = Form(""),
    q3_home_faceid: str = Form(""),
    q4_icloud: str = Form(""),
    q5_apple_body: str = Form(""),
    q6_apple_screen: str = Form(""),
    q7_apple_camera: str = Form(""),
    q8_apple_battery: str = Form(""),
    q5_android_camera: str = Form(""),
    q6_android_body: str = Form(""),
    q7_android_screen: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    clean_imei = imei.strip()
    answers = {
        "q1_working": q1_working,
        "q2_btk": q2_btk,
        "q3_home_faceid": q3_home_faceid,
        "q4_icloud": q4_icloud,
        "q5_apple_body": q5_apple_body,
        "q6_apple_screen": q6_apple_screen,
        "q7_apple_camera": q7_apple_camera,
        "q8_apple_battery": q8_apple_battery,
        "q5_android_camera": q5_android_camera,
        "q6_android_body": q6_android_body,
        "q7_android_screen": q7_android_screen
    }

    penalty = calculate_penalty_points(answers)
    calculated_price, diff_amount = calculate_valuation(full_price, penalty, voucher_amount)

    execute_db("""
    UPDATE mutabakat_records SET
        customer_name = ?, tc_no = ?, phone = ?, store_name = ?, process_user = ?, process_start_date = ?,
        imei = ?, brand = ?, model = ?, full_price = ?, voucher_amount = ?, voucher_no = ?,
        reconciliation_status = ?, screen_original = ?, camera_original = ?, battery_original = ?, notes = ?,
        q1_working = ?, q2_btk = ?, q3_home_faceid = ?, q4_icloud = ?,
        q5_apple_body = ?, q6_apple_screen = ?, q7_apple_camera = ?, q8_apple_battery = ?,
        q5_android_camera = ?, q6_android_body = ?, q7_android_screen = ?,
        penalty_points = ?, calculated_price = ?, difference_amount = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (
        customer_name.strip(), tc_no.strip(), phone.strip(), store_name.strip(), process_user.strip(), process_start_date,
        clean_imei, brand.strip(), model.strip(), full_price, voucher_amount, voucher_no.strip(),
        reconciliation_status, screen_original, camera_original, battery_original, notes.strip(),
        q1_working, q2_btk, q3_home_faceid, q4_icloud,
        q5_apple_body, q6_apple_screen, q7_apple_camera, q8_apple_battery,
        q5_android_camera, q6_android_body, q7_android_screen,
        penalty, calculated_price, diff_amount, record_id
    ))

    return RedirectResponse(
        url=f"/mutabakat/{record_id}?msg=Kayıt+başarıyla+güncellendi",
        status_code=status.HTTP_302_FOUND
    )


@app.post("/mutabakat/{record_id}/delete")
def delete_mutabakat_action(request: Request, record_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    execute_db("DELETE FROM mutabakat_records WHERE id = ?", (record_id,))
    return RedirectResponse(url="/mutabakat?msg=Kayıt+silindi", status_code=status.HTTP_302_FOUND)


# ----------------------------------------------------
# ADMIN GÜNLÜK EXCEL YÜKLEME & ÇİFT KAYIT ENGELLEME
# ----------------------------------------------------

@app.get("/import/daily", response_class=HTMLResponse)
def daily_import_page(request: Request, msg: Optional[str] = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard?msg=Günlük+veri+yükleme+yalnızca+Admin+yetkisindedir", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(request=request, name="daily_upload.html", context={
        "current_user": user,
        "active_page": "daily_upload",
        "upload_result": None,
        "message": msg
    })


@app.post("/import/daily", response_class=HTMLResponse)
async def daily_import_action(
    request: Request,
    file: UploadFile = File(...),
    duplicate_action: str = Form("skip")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard?msg=Günlük+veri+yükleme+yalnızca+Admin+yetkisindedir", status_code=status.HTTP_302_FOUND)

    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        return templates.TemplateResponse(request=request, name="daily_upload.html", context={
            "current_user": user,
            "active_page": "daily_upload",
            "upload_result": None,
            "message": "Lütfen geçerli bir Excel (.xlsx / .xls) veya CSV (.csv) dosyası seçin!",
            "message_type": "error"
        })

    file_bytes = await file.read()
    result = import_daily_excel(
        file_bytes=file_bytes,
        filename=file.filename,
        action_on_duplicate=duplicate_action,
        imported_by_user=user["full_name"]
    )

    msg = f"İşlem Tamamlandı: {result.get('imported_count', 0)} yeni cihaz kaydedildi, {result.get('skipped_duplicate_count', 0)} çift kayıt otomatik engellendi."
    return templates.TemplateResponse(request=request, name="daily_upload.html", context={
        "current_user": user,
        "active_page": "daily_upload",
        "upload_result": result,
        "message": msg,
        "message_type": "success" if result.get("success") else "error"
    })


# ----------------------------------------------------
# CANLI IMEI KONTROLÜ API
# ----------------------------------------------------

@app.get("/api/check-imei")
def check_imei_api(imei: str, exclude_id: Optional[int] = None):
    clean_imei = imei.strip()
    query = "SELECT id, store_name, customer_name, process_start_date FROM mutabakat_records WHERE imei = ?"
    params = [clean_imei]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)

    matches = query_all(query, tuple(params))
    if matches:
        first = matches[0]
        return JSONResponse({
            "is_duplicate": True,
            "count": len(matches),
            "store_name": first["store_name"] or "Bilinmiyor",
            "customer_name": first["customer_name"] or "",
            "date": first["process_start_date"] or ""
        })
    return JSONResponse({"is_duplicate": False, "count": 0})


# ----------------------------------------------------
# EXCEL DIŞA AKTARMA (RAPOR)
# ----------------------------------------------------

@app.get("/export/excel")
def export_excel_action(request: Request, status: str = "", store: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    excel_stream = generate_mutabakat_excel(status_filter=status, store_filter=store)
    filename = f"Teknosa_Mutabakat_Raporu_{date.today().strftime('%Y%m%d')}.xlsx"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
