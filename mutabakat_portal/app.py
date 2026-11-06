"""
Teknosa Mutabakat ve Hakediş Yönetim Portalı — FastAPI Ana Web Uygulaması
"""
from fastapi import FastAPI, Request, Response, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import date, timedelta, datetime
from typing import Optional, Dict, Any, List
import math
import uuid

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
from .services.daily_importer import (
    preview_daily_excel,
    import_daily_excel,
    get_last_active_batch,
    get_recent_batches,
    revert_last_import,
    revert_batch_by_id,
    recalculate_all_records,
    search_imeis_for_deletion,
    delete_records_by_ids
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMP_UPLOADS_DIR = BASE_DIR.parent / "data" / "temp_uploads"
TEMP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

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
# DASHBOARD & RAPORLAMA MERKEZİ
# ----------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_view(
    request: Request,
    response: Response,
    period: str = "all",
    start_date: str = "",
    end_date: str = "",
    store: str = "",
    rep: str = "",
    model: str = "",
    status: str = "",
    sort_by: str = "count",     # "count", "amount", "diff"
    view_tab: str = "store",    # "store", "rep", "model"
    refresh: Optional[str] = None
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    # Tarayıcı önbelleğini engelle (Her tıklandığında taze canlı veritabanı sorgusu)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    today = date.today()
    period_label = "Tüm Zamanlar"

    # Tarih aralığını belirle
    if period == "7d":
        start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_label = f"Haftalık (Son 7 Gün: {start_date} - {end_date})"
    elif period == "30d":
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_label = f"Aylık (Son 30 Gün: {start_date} - {end_date})"
    elif period == "90d":
        start_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_label = f"3 Aylık (Son 90 Gün: {start_date} - {end_date})"
    elif period == "custom" or (start_date or end_date):
        period = "custom"
        period_label = f"Özel Tarih ({start_date or 'Başlangıç'} - {end_date or 'Bitiş'})"
    else:
        period = "all"
        period_label = "Tüm Zamanlar"

    # Sıralama mantığı: Adet, Total Tutar veya Fark Tutarı
    if sort_by == "amount":
        order_clause = "total_voucher DESC"
        sort_label = "Total Çek Tutarına Göre (₺)"
    elif sort_by == "diff":
        order_clause = "ABS(total_diff) DESC"
        sort_label = "Fark Tutarına Göre (₺)"
    else:
        sort_by = "count"
        order_clause = "total DESC"
        sort_label = "İşlem Adedine Göre"

    # Güvenlik & Tutarlılık: IMEI'si silinmiş / boş kayıt varsa veritabanından kalıcı olarak temizle
    execute_db("DELETE FROM mutabakat_records WHERE imei IS NULL OR TRIM(imei) = '' OR LENGTH(TRIM(imei)) < 8 OR imei = '0' OR imei = '-';")

    # WHERE koşullarını oluştur (IMEI'si silinen / geçersiz olanlar raporlara dahil edilmez)
    where_clauses = [
        "1=1",
        "imei IS NOT NULL",
        "TRIM(imei) != ''",
        "LENGTH(TRIM(imei)) >= 8"
    ]
    params = []

    if start_date:
        where_clauses.append("substr(process_start_date, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("substr(process_start_date, 1, 10) <= ?")
        params.append(end_date)
    if store.strip():
        where_clauses.append("store_name = ?")
        params.append(store.strip())
    if rep.strip():
        where_clauses.append("process_user = ?")
        params.append(rep.strip())
    if model.strip():
        where_clauses.append("model = ?")
        params.append(model.strip())
    if status.strip():
        where_clauses.append("reconciliation_status = ?")
        params.append(status.strip())

    where_sql = " AND ".join(where_clauses)
    params_tuple = tuple(params)

    # 1. Ana KPI İstatistikleri (FARK VE UYUŞMAZLIK SADECE MUTABAKATI TAMAMLANANLAR İÇİN HESAPLANIR)
    stats_raw = query_one(f"""
    SELECT 
        COUNT(*) as total,
        COALESCE(SUM(voucher_amount), 0) as total_voucher,
        COALESCE(SUM(calculated_price), 0) as total_calculated,
        -- Kural: Fark hesabı sadece mutabakatı tamamlananlar için yapılmalı
        COALESCE(SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as total_diff,
        COALESCE(AVG(voucher_amount), 0) as avg_voucher,
        -- Kural: Uyuşmazlık adedi sadece mutabakatı tamamlananlar için sayılmalı
        SUM(CASE WHEN difference_amount != 0 AND reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as diff_count,
        SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as completed_count,
        SUM(CASE WHEN reconciliation_status = 'İptal' THEN 1 ELSE 0 END) as cancelled_count,
        SUM(CASE WHEN reconciliation_status = 'Cevap bekleniyor' OR reconciliation_status IS NULL OR reconciliation_status = '' THEN 1 ELSE 0 END) as waiting_count,
        COALESCE(SUM(CASE WHEN difference_amount < 0 AND reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as neg_diff_total,
        COALESCE(SUM(CASE WHEN difference_amount > 0 AND reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as pos_diff_total
    FROM mutabakat_records
    WHERE {where_sql}
    """, params_tuple)

    total_count = stats_raw["total"] or 0
    completed_count = stats_raw["completed_count"] or 0
    completed_pct = round((completed_count / total_count * 100), 1) if total_count > 0 else 0
    diff_count = stats_raw["diff_count"] or 0
    # Uyuşmazlık oranı tamamlanan işlemler içinde hesaplanır
    diff_pct = round((diff_count / completed_count * 100), 1) if completed_count > 0 else 0

    stats = {
        "total": total_count,
        "total_voucher": stats_raw["total_voucher"] or 0,
        "total_calculated": stats_raw["total_calculated"] or 0,
        "total_diff": stats_raw["total_diff"] or 0,
        "avg_voucher": round(stats_raw["avg_voucher"] or 0, 2),
        "completed_count": completed_count,
        "completed_pct": completed_pct,
        "waiting_count": stats_raw["waiting_count"] or 0,
        "cancelled_count": stats_raw["cancelled_count"] or 0,
        "diff_count": diff_count,
        "diff_pct": diff_pct,
        "neg_diff_total": stats_raw["neg_diff_total"] or 0,
        "pos_diff_total": stats_raw["pos_diff_total"] or 0,
    }

    # 2. Statü Dağılımı
    status_counts = query_all(f"""
    SELECT reconciliation_status, COUNT(*) as c 
    FROM mutabakat_records 
    WHERE {where_sql}
    GROUP BY reconciliation_status 
    ORDER BY c DESC
    """, params_tuple)
    stats["status_counts"] = status_counts

    # 3. Marka Dağılımı
    brand_counts = query_all(f"""
    SELECT brand, COUNT(*) as c, COALESCE(SUM(voucher_amount), 0) as total_voucher
    FROM mutabakat_records 
    WHERE {where_sql} AND brand != '' 
    GROUP BY brand 
    ORDER BY c DESC 
    LIMIT 6
    """, params_tuple)
    stats["brand_counts"] = brand_counts

    # 4. Zaman Serisi Trendi (Grafik İçin)
    is_daily = False
    if period in ["7d", "30d"]:
        is_daily = True
    elif start_date and end_date:
        try:
            d_start = datetime.strptime(start_date, "%Y-%m-%d")
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            if (d_end - d_start).days <= 45:
                is_daily = True
        except Exception:
            pass

    trend_group = "substr(process_start_date, 1, 10)" if is_daily else "substr(process_start_date, 1, 7)"
    trend_rows = query_all(f"""
    SELECT 
        {trend_group} as label,
        COUNT(*) as count,
        COALESCE(SUM(voucher_amount), 0) as voucher,
        COALESCE(SUM(calculated_price), 0) as calculated,
        COALESCE(SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as diff
    FROM mutabakat_records
    WHERE {where_sql} AND process_start_date != ''
    GROUP BY {trend_group}
    ORDER BY label ASC
    """, params_tuple)

    # 5. Mağaza Performans Tablosu (Top 20)
    store_performance = query_all(f"""
    SELECT 
        store_name,
        COUNT(*) as total,
        COALESCE(SUM(voucher_amount), 0) as total_voucher,
        COALESCE(SUM(calculated_price), 0) as total_calculated,
        COALESCE(SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as total_diff,
        SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as completed_count
    FROM mutabakat_records
    WHERE {where_sql} AND store_name != ''
    GROUP BY store_name
    ORDER BY {order_clause}
    LIMIT 20
    """, params_tuple)

    # 6. Temsilci Performans Tablosu (Top 20)
    rep_performance = query_all(f"""
    SELECT 
        process_user,
        store_name,
        COUNT(*) as total,
        COALESCE(SUM(voucher_amount), 0) as total_voucher,
        COALESCE(SUM(calculated_price), 0) as total_calculated,
        COALESCE(SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as total_diff,
        SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as completed_count
    FROM mutabakat_records
    WHERE {where_sql} AND process_user != ''
    GROUP BY process_user, store_name
    ORDER BY {order_clause}
    LIMIT 20
    """, params_tuple)

    # 7. Model Performans Tablosu (Top 20)
    model_performance = query_all(f"""
    SELECT 
        model,
        brand,
        COUNT(*) as total,
        COALESCE(SUM(voucher_amount), 0) as total_voucher,
        COALESCE(SUM(calculated_price), 0) as total_calculated,
        COALESCE(SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as total_diff,
        SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as completed_count
    FROM mutabakat_records
    WHERE {where_sql} AND model != ''
    GROUP BY model
    ORDER BY {order_clause}
    LIMIT 20
    """, params_tuple)

    # 8. En yüksek fark çıkan işlemler (SADECE MUTABAKATI TAMAMLANANLAR)
    top_diff_records = query_all(f"""
    SELECT id, imei, customer_name, brand, model, store_name, process_user,
           voucher_amount, calculated_price, difference_amount, reconciliation_status,
           process_start_date
    FROM mutabakat_records
    WHERE {where_sql} AND reconciliation_status = 'Mutabakat tamamlandı' AND difference_amount != 0
    ORDER BY ABS(difference_amount) DESC
    LIMIT 10
    """, params_tuple)

    # 9. Filtre Seçenekleri: Mağaza, Temsilci, Model
    all_stores = query_all("""
    SELECT DISTINCT store_name, COUNT(*) as c 
    FROM mutabakat_records 
    WHERE store_name != '' 
    GROUP BY store_name 
    ORDER BY store_name ASC
    """)

    all_models = query_all("""
    SELECT DISTINCT model, brand, COUNT(*) as c 
    FROM mutabakat_records 
    WHERE model != '' 
    GROUP BY model 
    ORDER BY c DESC 
    LIMIT 300
    """)

    # Eğer mağaza seçildiyse onun temsilcileri, değilse tüm temsilciler
    if store.strip():
        all_reps = query_all("""
        SELECT DISTINCT process_user, COUNT(*) as c 
        FROM mutabakat_records 
        WHERE process_user != '' AND store_name = ?
        GROUP BY process_user 
        ORDER BY process_user ASC
        """, (store.strip(),))
    else:
        all_reps = query_all("""
        SELECT DISTINCT process_user, store_name, COUNT(*) as c 
        FROM mutabakat_records 
        WHERE process_user != '' 
        GROUP BY process_user 
        ORDER BY c DESC 
        LIMIT 250
        """)

    resp_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "current_user": user,
        "active_page": "dashboard",
        "stats": stats,
        "trend_rows": trend_rows,
        "is_daily": is_daily,
        "store_performance": store_performance,
        "rep_performance": rep_performance,
        "model_performance": model_performance,
        "top_diff_records": top_diff_records,
        "all_stores": all_stores,
        "all_reps": all_reps,
        "all_models": all_models,
        "selected_period": period,
        "period_label": period_label,
        "start_date": start_date,
        "end_date": end_date,
        "selected_store": store.strip(),
        "selected_rep": rep.strip(),
        "selected_model": model.strip(),
        "selected_status": status.strip(),
        "sort_by": sort_by,
        "sort_label": sort_label,
        "view_tab": view_tab,
        "today_str": today.strftime("%d.%m.%Y"),
        "last_updated_time": datetime.now().strftime("%H:%M:%S"),
        "is_refreshed": (refresh == "1")
    }, headers=resp_headers)


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
    store: str = "",
    rep: str = "",
    model: str = "",
    period: str = "",
    start_date: str = "",
    end_date: str = "",
    msg: Optional[str] = None
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    today = date.today()
    if period == "7d":
        start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif period == "30d":
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif period == "90d":
        start_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    page_size = 50
    offset = max(0, (page - 1) * page_size)

    where_clauses = [
        "1=1",
        "imei IS NOT NULL",
        "TRIM(imei) != ''",
        "LENGTH(TRIM(imei)) >= 8"
    ]
    params = []

    if q.strip():
        search_term = f"%{q.strip()}%"
        where_clauses.append("(imei LIKE ? OR customer_name LIKE ? OR store_name LIKE ? OR model LIKE ?)")
        params.extend([search_term, search_term, search_term, search_term])

    if status.strip():
        where_clauses.append("reconciliation_status = ?")
        params.append(status.strip())

    if store.strip():
        where_clauses.append("store_name = ?")
        params.append(store.strip())

    if rep.strip():
        where_clauses.append("process_user = ?")
        params.append(rep.strip())

    if model.strip():
        where_clauses.append("model = ?")
        params.append(model.strip())

    if start_date:
        where_clauses.append("substr(process_start_date, 1, 10) >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("substr(process_start_date, 1, 10) <= ?")
        params.append(end_date)

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
    SELECT id, imei, is_duplicate, customer_name, phone, tc_no, store_name, process_user,
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
        "store_filter": store,
        "rep_filter": rep,
        "model_filter": model,
        "period_filter": period,
        "start_date": start_date,
        "end_date": end_date,
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
    customer_name: str = Form(""),
    tc_no: str = Form(""),
    phone: str = Form(""),
    store_name: str = Form(""),
    process_user: str = Form(""),
    process_start_date: str = Form(""),
    imei: str = Form(""),
    brand: str = Form(""),
    model: str = Form(""),
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

    # Kural: IMEI silindiyse satıra ait tüm veri veritabanından kalıcı olarak silinmeli, raporlarda çıkmamalı
    if not clean_imei or len(clean_imei) < 8 or clean_imei.lower() in ("0", "-", "yok", "silindi", "silinmis", "iptal"):
        execute_db("DELETE FROM mutabakat_records WHERE id = ?", (record_id,))
        return RedirectResponse(
            url="/mutabakat?msg=IMEI+silindiği+için+ilgili+cihaza+ait+tüm+veriler+veritabanından+kalıcı+olarak+silindi",
            status_code=status.HTTP_302_FOUND
        )

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
# ADMIN GÜNLÜK EXCEL YÜKLEME, 2 ADIMLI KONTROL & GERİ ALMA
# ----------------------------------------------------

@app.get("/import/daily", response_class=HTMLResponse)
def daily_import_page(request: Request, msg: Optional[str] = None, msg_type: str = "success"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard?msg=Günlük+veri+yükleme+yalnızca+Admin+yetkisindedir", status_code=status.HTTP_302_FOUND)

    last_batch = get_last_active_batch()

    return templates.TemplateResponse(request=request, name="daily_upload.html", context={
        "current_user": user,
        "active_page": "daily_upload",
        "last_batch": last_batch,
        "preview_result": None,
        "preview_token": None,
        "upload_result": None,
        "message": msg,
        "message_type": msg_type
    })


@app.post("/import/daily/check", response_class=HTMLResponse)
async def daily_import_check(
    request: Request,
    file: UploadFile = File(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    last_batch = get_last_active_batch()

    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        return templates.TemplateResponse(request=request, name="daily_upload.html", context={
            "current_user": user,
            "active_page": "daily_upload",
            "last_batch": last_batch,
            "preview_result": None,
            "preview_token": None,
            "upload_result": None,
            "message": "Lütfen geçerli bir Excel (.xlsx / .xls) veya CSV (.csv) dosyası seçin!",
            "message_type": "error"
        })

    file_bytes = await file.read()
    preview = preview_daily_excel(file_bytes=file_bytes, filename=file.filename)

    if not preview.get("success"):
        return templates.TemplateResponse(request=request, name="daily_upload.html", context={
            "current_user": user,
            "active_page": "daily_upload",
            "last_batch": last_batch,
            "preview_result": None,
            "preview_token": None,
            "upload_result": None,
            "message": f"Kontrol Başarısız: {preview.get('error', 'Dosya okunamadı')}",
            "message_type": "error"
        })

    # Dosyayı geçici klasöre kaydet (2. Adım için hazır tut)
    preview_token = str(uuid.uuid4())
    bin_path = TEMP_UPLOADS_DIR / f"{preview_token}.bin"
    meta_path = TEMP_UPLOADS_DIR / f"{preview_token}.meta"

    try:
        bin_path.write_bytes(file_bytes)
        meta_path.write_text(file.filename, encoding="utf-8")
    except Exception as e:
        return templates.TemplateResponse(request=request, name="daily_upload.html", context={
            "current_user": user,
            "active_page": "daily_upload",
            "last_batch": last_batch,
            "preview_result": None,
            "preview_token": None,
            "upload_result": None,
            "message": f"Geçici dosya oluşturulamadı: {str(e)}",
            "message_type": "error"
        })

    return templates.TemplateResponse(request=request, name="daily_upload.html", context={
        "current_user": user,
        "active_page": "daily_upload",
        "last_batch": last_batch,
        "preview_result": preview,
        "preview_token": preview_token,
        "upload_result": None,
        "message": f"Dosya Başarıyla Kontrol Edildi: {preview['valid_count']} cihaz incelendi ({preview['new_count']} yeni, {preview['duplicate_count']} mükerrer). Şimdi aktarımı onaylayabilirsiniz.",
        "message_type": "success"
    })


@app.post("/import/daily/commit", response_class=HTMLResponse)
async def daily_import_commit(
    request: Request,
    preview_token: str = Form(...),
    duplicate_action: str = Form("skip")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    bin_path = TEMP_UPLOADS_DIR / f"{preview_token}.bin"
    meta_path = TEMP_UPLOADS_DIR / f"{preview_token}.meta"

    if not bin_path.exists():
        last_batch = get_last_active_batch()
        return templates.TemplateResponse(request=request, name="daily_upload.html", context={
            "current_user": user,
            "active_page": "daily_upload",
            "last_batch": last_batch,
            "preview_result": None,
            "preview_token": None,
            "upload_result": None,
            "message": "Kontrol oturumu zaman aşımına uğramış veya bulunamadı. Lütfen dosyayı tekrar seçip 'Kontrol Et' butonuna basınız.",
            "message_type": "error"
        })

    file_bytes = bin_path.read_bytes()
    filename = meta_path.read_text(encoding="utf-8") if meta_path.exists() else "yuklenen_dosya.xlsx"

    # Aktarımı gerçekleştir
    result = import_daily_excel(
        file_bytes=file_bytes,
        filename=filename,
        action_on_duplicate=duplicate_action,
        imported_by_user=user["full_name"]
    )

    # Geçici dosyaları temizle
    try:
        bin_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    except Exception:
        pass

    last_batch = get_last_active_batch()
    msg = f"Aktarım Tamamlandı (Paket: {result.get('batch_id')}): {result.get('imported_count', 0)} yeni cihaz başarıyla sisteme kaydedildi, {result.get('skipped_duplicate_count', 0)} çift kayıt engellendi."

    return templates.TemplateResponse(request=request, name="daily_upload.html", context={
        "current_user": user,
        "active_page": "daily_upload",
        "last_batch": last_batch,
        "preview_result": None,
        "preview_token": None,
        "upload_result": result,
        "message": msg,
        "message_type": "success" if result.get("success") else "error"
    })


@app.post("/import/revert-last")
def revert_last_import_action(request: Request):
    """En son yapılan aktarımı ve kayıtlarını geri alır."""
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/login")

    res = revert_last_import(reverted_by=user["full_name"])
    if res.get("success"):
        return RedirectResponse(url=f"/import/daily?msg={res.get('message')}&msg_type=success", status_code=status.HTTP_302_FOUND)
    else:
        return RedirectResponse(url=f"/import/daily?msg={res.get('error')}&msg_type=error", status_code=status.HTTP_302_FOUND)


@app.post("/import/revert-batch")
def revert_batch_action(request: Request, batch_id: str = Form(...)):
    """Belirli bir aktarım paketini ID'sine göre geri alır."""
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/login")

    res = revert_batch_by_id(batch_id=batch_id.strip(), reverted_by=user["full_name"])
    msg_type = "success" if res.get("success") else "error"
    msg_text = res.get("message") if res.get("success") else res.get("error")
    return RedirectResponse(url=f"/admin/bulk-delete?msg={msg_text}&msg_type={msg_type}", status_code=status.HTTP_302_FOUND)


@app.post("/admin/recalculate-all")
def recalculate_all_action(request: Request):
    """Tüm veritabanındaki hakediş, soru puanları ve farkları yeniden hesaplar."""
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/login")

    res = recalculate_all_records()
    return RedirectResponse(url=f"/import/daily?msg={res.get('message')}&msg_type=success", status_code=status.HTTP_302_FOUND)


# ----------------------------------------------------
# TOPLU SERİ / IMEI SİLME VE PAKET YÖNETİMİ
# ----------------------------------------------------

@app.get("/admin/bulk-delete", response_class=HTMLResponse)
def bulk_delete_page(request: Request, msg: Optional[str] = None, msg_type: str = "success"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard?msg=Toplu+silme+yalnızca+Admin+yetkisindedir")

    recent_batches = get_recent_batches(20)

    return templates.TemplateResponse(request=request, name="bulk_delete.html", context={
        "current_user": user,
        "active_page": "bulk_delete",
        "recent_batches": recent_batches,
        "search_result": None,
        "searched_text": "",
        "message": msg,
        "message_type": msg_type
    })


@app.post("/admin/bulk-delete/search", response_class=HTMLResponse)
async def bulk_delete_search_action(
    request: Request,
    imeis_text: str = Form(""),
    file: Optional[UploadFile] = File(None)
):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/login")

    combined_input = imeis_text

    # Eğer dosya yüklendiyse içindeki metni ekle
    if file and file.filename:
        file_bytes = await file.read()
        try:
            if file.filename.lower().endswith((".xlsx", ".xls")):
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
                ws = wb.active
                extracted = []
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell:
                            s = str(cell).strip()
                            if len(s) >= 8 and s.isdigit():
                                extracted.append(s)
                combined_input += "\n" + "\n".join(extracted)
            else:
                for enc in ("utf-8-sig", "utf-8", "cp1254"):
                    try:
                        text = file_bytes.decode(enc)
                        combined_input += "\n" + text
                        break
                    except Exception:
                        continue
        except Exception:
            pass

    search_res = search_imeis_for_deletion(combined_input)
    recent_batches = get_recent_batches(20)

    msg = None
    msg_type = "success"
    if not search_res.get("success"):
        msg = search_res.get("error")
        msg_type = "error"
    else:
        msg = f"Arama Tamamlandı: {search_res['total_searched']} adet IMEI arandı, {search_res['matched_count']} eşleşen kayıt bulundu ({search_res['not_found_count']} kayıt veritabanında yok)."

    return templates.TemplateResponse(request=request, name="bulk_delete.html", context={
        "current_user": user,
        "active_page": "bulk_delete",
        "recent_batches": recent_batches,
        "search_result": search_res if search_res.get("success") else None,
        "searched_text": imeis_text,
        "message": msg,
        "message_type": msg_type
    })


@app.post("/admin/bulk-delete/confirm")
def bulk_delete_confirm_action(
    request: Request,
    selected_ids: List[int] = Form(...)
):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/login")

    deleted = delete_records_by_ids(selected_ids)
    msg = f"Seçilen {deleted} adet cihaz kaydı veritabanından kalıcı olarak silindi."
    return RedirectResponse(url=f"/admin/bulk-delete?msg={msg}&msg_type=success", status_code=status.HTTP_302_FOUND)


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
def export_excel_action(
    request: Request,
    status: str = "",
    store: str = "",
    rep: str = "",
    model: str = "",
    period: str = "all",
    start_date: str = "",
    end_date: str = ""
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    today = date.today()
    period_label = "Tüm Zamanlar"

    if period == "7d":
        start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_label = f"Haftalık (Son 7 Gün: {start_date} - {end_date})"
    elif period == "30d":
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_label = f"Aylık (Son 30 Gün: {start_date} - {end_date})"
    elif period == "90d":
        start_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_label = f"3 Aylık (Son 90 Gün: {start_date} - {end_date})"
    elif period == "custom" or (start_date or end_date):
        period_label = f"Özel Tarih ({start_date or 'Başlangıç'} - {end_date or 'Bitiş'})"

    excel_stream = generate_mutabakat_excel(
        status_filter=status,
        store_filter=store,
        rep_filter=rep,
        model_filter=model,
        start_date=start_date,
        end_date=end_date,
        period_label=period_label
    )

    clean_store = f"_{store[:10].replace(' ', '_')}" if store else ""
    clean_rep = f"_{rep[:10].replace(' ', '_')}" if rep else ""
    clean_model = f"_{model[:10].replace(' ', '_')}" if model else ""
    filename = f"Teknosa_Mutabakat_Raporu_{period}{clean_store}{clean_rep}{clean_model}_{today.strftime('%Y%m%d')}.xlsx"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
