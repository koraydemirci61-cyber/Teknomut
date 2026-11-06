"""
Teknosa Mutabakat Verilerini Excel (.xlsx) Olarak Dışa Aktarma Servisi
Yüksek performanslı write_only akışı kullanır.
"""
import io
import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime
from ..database import query_all


def generate_mutabakat_excel(
    status_filter: str = "",
    store_filter: str = "",
    rep_filter: str = "",
    model_filter: str = "",
    start_date: str = "",
    end_date: str = "",
    period_label: str = ""
) -> io.BytesIO:
    """Veritabanındaki güncel mutabakat kayıtlarını kurumsal Excel dosyasına dönüştürür."""
    wb = openpyxl.Workbook(write_only=True)

    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    sub_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    sub_font = Font(name="Calibri", size=10, bold=True, color="000000")
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    # Filtreli sorgu oluştur (IMEI'si silinen veya geçersiz olanlar kesinlikle dahil edilmez)
    where_clauses = [
        "1=1",
        "imei IS NOT NULL",
        "TRIM(imei) != ''",
        "LENGTH(TRIM(imei)) >= 8"
    ]
    params = []
    if status_filter:
        where_clauses.append("reconciliation_status = ?")
        params.append(status_filter)
    if store_filter:
        where_clauses.append("store_name = ?")
        params.append(store_filter)
    if rep_filter:
        where_clauses.append("process_user = ?")
        params.append(rep_filter)
    if model_filter:
        where_clauses.append("model = ?")
        params.append(model_filter)
    if start_date:
        where_clauses.append("substr(process_start_date, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("substr(process_start_date, 1, 10) <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses)
    params_tuple = tuple(params)

    # ----------------------------------------------------
    # SAYFA 1: ÖZET RAPOR (YÖNETİCİ GÖRÜNÜMÜ)
    # ----------------------------------------------------
    ws_summary = wb.create_sheet(title="YÖNETİCİ ÖZETİ")
    summary_headers = ["Rapor Parametresi / Gösterge", "Değer / Bilgi"]
    row_cells = []
    for h in summary_headers:
        c = WriteOnlyCell(ws_summary, value=h)
        c.font = header_font
        c.fill = header_fill
        row_cells.append(c)
    ws_summary.append(row_cells)

    # İstatistikleri hesapla - FARK VE UYUŞMAZLIK SADECE MUTABAKATI TAMAMLANANLAR İÇİN
    from ..database import query_one
    stats = query_one(f"""
    SELECT 
        COUNT(*) as total,
        COALESCE(SUM(voucher_amount), 0) as total_voucher,
        COALESCE(SUM(calculated_price), 0) as total_calculated,
        COALESCE(SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN difference_amount ELSE 0 END), 0) as total_diff,
        COALESCE(AVG(voucher_amount), 0) as avg_voucher,
        SUM(CASE WHEN reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as completed_count,
        SUM(CASE WHEN reconciliation_status = 'İptal' THEN 1 ELSE 0 END) as cancelled_count,
        SUM(CASE WHEN difference_amount != 0 AND reconciliation_status = 'Mutabakat tamamlandı' THEN 1 ELSE 0 END) as diff_count
    FROM mutabakat_records
    WHERE {where_sql}
    """, params_tuple)

    total_cnt = stats["total"] if stats else 0
    comp_cnt = stats["completed_count"] if stats else 0
    comp_pct = round((comp_cnt / total_cnt * 100), 1) if total_cnt > 0 else 0

    summary_rows = [
        ["Rapor Türü", "Teknosa Mutabakat ve Hakediş Yönetim Raporu"],
        ["Raporlama Tarihi", datetime.now().strftime("%d.%m.%Y %H:%M")],
        ["Raporlanan Dönem", period_label or ("Tüm Zamanlar" if not start_date and not end_date else f"{start_date} - {end_date}")],
        ["Mağaza Filtresi", store_filter or "Tüm Mağazalar"],
        ["Temsilci Filtresi", rep_filter or "Tüm Temsilciler"],
        ["Model Filtresi", model_filter or "Tüm Modeller"],
        ["Statü Filtresi", status_filter or "Tüm Statüler"],
        ["", ""],
        ["TOPLAM İŞLEM ADEDİ", total_cnt],
        ["MÜŞTERİYE VERİLEN ÇEK TOPLAMI (₺)", stats["total_voucher"] if stats else 0],
        ["HESAPLANAN HAKEDİŞ DEĞERİ (₺)", stats["total_calculated"] if stats else 0],
        ["TOPLAM NET FARK (Sadece Mutabakatı Tamamlananlar) (₺)", stats["total_diff"] if stats else 0],
        ["ORTALAMA CİHAZ ÇEK TUTARI (₺)", round(stats["avg_voucher"], 2) if stats else 0],
        ["MUTABAKATI TAMAMLANAN CİHAZ ADEDİ", comp_cnt],
        ["MUTABAKAT TAMAMLANMA ORANI (%)", f"%{comp_pct}"],
        ["UYUŞMAZLIK / FARK ÇIKAN CİHAZ (Mutabakatı Tamamlananlar)", stats["diff_count"] if stats else 0],
        ["İPTAL EDİLEN İŞLEM ADEDİ", stats["cancelled_count"] if stats else 0]
    ]

    for item in summary_rows:
        c1 = WriteOnlyCell(ws_summary, value=item[0])
        c2 = WriteOnlyCell(ws_summary, value=item[1])
        if item[0].startswith("TOPLAM") or item[0].startswith("MÜŞTERİYE") or item[0].startswith("HESAPLANAN"):
            c1.font = sub_font
            c1.fill = sub_fill
            c2.font = sub_font
        ws_summary.append([c1, c2])

    # ----------------------------------------------------
    # SAYFA 2: MUTABAKAT DETAYLARI
    # ----------------------------------------------------
    ws = wb.create_sheet(title="MUTABAKAT DETAYI")

    headers = [
        "Müşteri Adı Soyadı", "T.C. Kimlik No", "Müşteri Telefon", "Adres", "Email",
        "Product ID", "IMEI", "Çift Adet Kontrol", "Wega Kaydı", "Ürün No",
        "Marka", "Model", "Durum", "Teslim Bilgisi", "Teslim Tarihi",
        "Takip Numarası", "Teslim Eden Kullanıcı", "İptal Nedeni", "Çek Bilgisi", "Çek Prefix",
        "Çek Tutarı", "Çek Durum", "Başlangıç Tarih", "Bitiş Tarih", "Sipariş No",
        "Sipariş Tutarı", "Sipariş Tarihi", "İşlem Tarihi", "İşlemi Yapan", "Mağaza Id",
        "Mağaza", "Firma Adı", "FİYAT (Hakediş)", "EKSİ PUAN", "TAM DEĞER",
        "Fark", "Statü", "Ekran Orijinal", "Kamera Orijinal", "Pil Orijinal", "Açıklama"
    ]

    header_cells = []
    for h in headers:
        c = WriteOnlyCell(ws, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        header_cells.append(c)
    ws.append(header_cells)

    rows = query_all(f"SELECT * FROM mutabakat_records WHERE {where_sql} ORDER BY id DESC", params_tuple)

    for r in rows:
        vals = [
            r["customer_name"], r["tc_no"], r["phone"], r["address"], r["email"],
            r["product_id"], r["imei"], "ÇİFT İMEİ" if r["is_duplicate"] else "1",
            r["wega_record"], r["product_no"], r["brand"], r["model"], r["status"],
            r["delivery_info"], r["delivery_date"], r["tracking_no"], r["delivery_user"],
            r["cancel_reason"], r["voucher_no"], r["voucher_prefix"], r["voucher_amount"],
            r["voucher_status"], r["start_date"], r["end_date"], r["order_no"],
            r["order_amount"], r["order_date"], r["process_start_date"], r["process_user"],
            r["store_id"], r["store_name"], r["company_name"], r["calculated_price"],
            r["penalty_points"], r["full_price"], r["difference_amount"],
            r["reconciliation_status"], r["screen_original"], r["camera_original"],
            r["battery_original"], r["notes"]
        ]
        ws.append(vals)

    # ----------------------------------------------------
    # SAYFA 3: MAĞAZA PERFORMANSI
    # ----------------------------------------------------
    ws_store = wb.create_sheet(title="MAĞAZA PERFORMANSI")
    store_headers = ["Mağaza Adı", "İşlem Adedi", "Verilen Çek Tutarı (₺)", "Hesaplanan Hakediş (₺)", "Net Fark (₺) (Tamamlananlar)", "Tamamlanan İşlem"]
    row_cells = []
    for h in store_headers:
        c = WriteOnlyCell(ws_store, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        row_cells.append(c)
    ws_store.append(row_cells)

    store_rows = query_all(f"""
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
    ORDER BY total DESC
    """, params_tuple)

    for sr in store_rows:
        ws_store.append([
            sr["store_name"],
            sr["total"],
            sr["total_voucher"],
            sr["total_calculated"],
            sr["total_diff"],
            sr["completed_count"]
        ])

    # ----------------------------------------------------
    # SAYFA 4: TEMSİLCİ PERFORMANSI
    # ----------------------------------------------------
    ws_rep = wb.create_sheet(title="TEMSİLCİ PERFORMANSI")
    rep_headers = ["Temsilci (İşlemi Yapan)", "Mağaza", "İşlem Adedi", "Verilen Çek Tutarı (₺)", "Hesaplanan Hakediş (₺)", "Net Fark (₺) (Tamamlananlar)", "Tamamlanan İşlem"]
    row_cells = []
    for h in rep_headers:
        c = WriteOnlyCell(ws_rep, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        row_cells.append(c)
    ws_rep.append(row_cells)

    rep_rows = query_all(f"""
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
    ORDER BY total DESC
    """, params_tuple)

    for rr in rep_rows:
        ws_rep.append([
            rr["process_user"],
            rr["store_name"],
            rr["total"],
            rr["total_voucher"],
            rr["total_calculated"],
            rr["total_diff"],
            rr["completed_count"]
        ])

    # ----------------------------------------------------
    # SAYFA 5: MODEL PERFORMANSI
    # ----------------------------------------------------
    ws_model = wb.create_sheet(title="MODEL PERFORMANSI")
    model_headers = ["Model", "Marka", "İşlem Adedi", "Verilen Çek Tutarı (₺)", "Hesaplanan Hakediş (₺)", "Net Fark (₺) (Tamamlananlar)", "Tamamlanan İşlem"]
    row_cells = []
    for h in model_headers:
        c = WriteOnlyCell(ws_model, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        row_cells.append(c)
    ws_model.append(row_cells)

    model_rows = query_all(f"""
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
    ORDER BY total DESC
    """, params_tuple)

    for mr in model_rows:
        ws_model.append([
            mr["model"],
            mr["brand"],
            mr["total"],
            mr["total_voucher"],
            mr["total_calculated"],
            mr["total_diff"],
            mr["completed_count"]
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
