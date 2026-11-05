"""
Admin Günlük Excel Veri Yükleme ve Çift Kayıt Engelleme Servisi
Destek / Günlük Gelen Excel Formatı (Destek Kasım Data.xlsx vb.)
"""
import openpyxl
import io
import math
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from ..database import get_connection


def normalize_header(s: str) -> str:
    s = str(s).strip().upper()
    for src, dst in [('Ç', 'C'), ('Ğ', 'G'), ('İ', 'I'), ('Ö', 'O'), ('Ş', 'S'), ('Ü', 'U')]:
        s = s.replace(src, dst)
    return s.replace(' ', '_')


def clean_val_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            val = int(val)
        else:
            return f"{val:.2f}"
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d %H:%M:%S") if isinstance(val, datetime) and (val.hour or val.minute) else val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def clean_val_num(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def import_daily_excel(
    file_bytes: bytes,
    filename: str = "",
    action_on_duplicate: str = "skip", # "skip" (varsayılan) veya "update"
    imported_by_user: str = "admin"
) -> Dict[str, Any]:
    """
    Admin tarafından yüklenen günlük veriyi işler.
    Çift kayıt (mükerrer IMEI) kontrolünü otomatik yapar.
    Excel (.xlsx, .xls) ve CSV dosyalarını destekler.
    """
    # CSV / Excel ayrıştırma
    rows_iter = None
    header_row = None

    if filename.lower().endswith(".csv") or (not filename.lower().endswith((".xlsx", ".xls")) and file_bytes[:2] != b"PK"):
        import csv
        for enc in ("utf-8-sig", "utf-8", "cp1254", "iso-8859-9"):
            try:
                text = file_bytes.decode(enc)
                sample = text[:2000]
                delimiter = ";" if sample.count(";") > sample.count(",") else ","
                reader = csv.reader(text.splitlines(), delimiter=delimiter)
                csv_rows = [r for r in reader if any(cell.strip() for cell in r)]
                if csv_rows:
                    header_row = csv_rows[0]
                    rows_iter = iter(csv_rows[1:])
                    break
            except (UnicodeDecodeError, Exception):
                continue

    if header_row is None:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            header_row = next(rows_iter)
        except Exception as e:
            return {"success": False, "error": f"Dosya okunamadı: {str(e)}"}

    if not header_row:
        return {"success": False, "error": "Excel dosyası boş veya başlıklar bulunamadı!"}

    # Başlık eşleme (büyük harf ve Türkçe harfsiz karşılaştırma)
    col_map = {}
    for idx, h in enumerate(header_row):
        if not h:
            continue
        h_norm = normalize_header(str(h))
        col_map[h_norm] = idx

    # Kolon indekslerini bul (Esnek isim desteği)
    def find_col(*aliases):
        for a in aliases:
            a_norm = normalize_header(a)
            if a_norm in col_map:
                return col_map[a_norm]
        return None

    idx_customer = find_col("MUSTERI", "MUSTERI_ADI_SOYADI", "AD_SOYAD", "CUSTOMER")
    idx_tc = find_col("TCKN", "TC_NO", "TC_KIMLIK", "TC")
    idx_phone = find_col("CEP_TELEFONU", "TELEFON", "PHONE", "MUSTERI_TELEFON")
    idx_email = find_col("EMAIL", "E_POSTA", "E-MAIL")
    idx_address = find_col("ADRES", "ADDRESS")
    idx_prod_id = find_col("PRODUCT_ID", "URUN_ID", "PRODUCT")
    idx_imei = find_col("IMEI", "SERI_NO", "SERIAL")
    idx_brand = find_col("MARKA", "BRAND")
    idx_model = find_col("MODEL")
    idx_status = find_col("DURUM", "STATUS")
    idx_delivered = find_col("TESLIM_EDILDI", "TESLIM_BILGISI", "DELIVERY")
    idx_deliv_date = find_col("TESLIM_TARIHI", "DELIVERY_DATE")
    idx_track_no = find_col("TAKIP_NUMARASI", "TRACKING_NO", "KARGO_TAKIP")
    idx_cancel_reason = find_col("CANCEL_REASON", "IPTAL_NEDENI")
    idx_seq = find_col("SEQ", "CEK_PREFIX", "PREFIX")
    idx_voucher_no = find_col("CEK_PREFIX", "VOUCHER_NO", "CEK_NO", "SEQ")
    idx_voucher_amt = find_col("BUYBACK_TUTARI", "CEK_TUTARI", "TUTAR", "AMOUNT")
    idx_voucher_status = find_col("SEQ_STATUS", "CEK_DURUM")
    idx_start_date = find_col("BASLANGIC_TARIHI", "START_DATE")
    idx_end_date = find_col("BITIS_TARIHI", "END_DATE")
    idx_order_no = find_col("SIPARIS_ID", "SIPARIS_NO", "ORDER_NO")
    idx_order_date = find_col("SIPARIS_TARIHI", "ORDER_DATE")
    idx_proc_start = find_col("ISLEM_BASLANGIC", "ISLEM_TARIHI")
    idx_user = find_col("MUSTERI_TEMSILCISI", "ISLEMI_YAPAN", "USER")
    idx_store = find_col("SIPARIS_MAGAZA", "MAGAZA", "MAGAZA_ADI", "STORE")
    idx_company = find_col("FIRMA_ADI", "FIRMA", "COMPANY")
    idx_sent = find_col("SENT")

    if idx_imei is None:
        return {"success": False, "error": "Excel tablosunda 'IMEI' sütunu bulunamadı!"}

    conn = get_connection()
    cur = conn.cursor()

    # Mevcut model tavan fiyatları haritası
    cur.execute("SELECT LOWER(model_name), full_price FROM model_prices")
    price_map = {row[0].strip(): row[1] for row in cur.fetchall()}

    # Veritabanındaki tüm IMEI'leri çek (Hızlı hafıza kontrolü)
    cur.execute("SELECT imei, id, store_name, customer_name FROM mutabakat_records WHERE imei != ''")
    existing_db_imeis = {}
    for r in cur.fetchall():
        existing_db_imeis[r["imei"].strip()] = {
            "id": r["id"],
            "store_name": r["store_name"] or "",
            "customer_name": r["customer_name"] or ""
        }

    seen_in_batch = set()
    imported_records = []
    skipped_duplicates = []
    updated_records = []
    row_index = 1 # Header was row 1

    insert_sql = """
    INSERT INTO mutabakat_records (
        customer_name, tc_no, phone, email, address, product_id, imei, is_duplicate,
        brand, model, status, delivery_info, delivery_date, tracking_no, cancel_reason,
        voucher_prefix, voucher_no, voucher_amount, voucher_status, start_date, end_date,
        order_no, order_date, process_start_date, process_user, store_name, company_name, sent,
        full_price, calculated_price, penalty_points, difference_amount, reconciliation_status,
        notes
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?
    )
    """

    for row in rows_iter:
        row_index += 1
        if not any(row):
            continue

        raw_imei = clean_val_str(row[idx_imei] if idx_imei is not None and idx_imei < len(row) else "")
        if not raw_imei:
            continue

        cust_name = clean_val_str(row[idx_customer]) if idx_customer is not None and idx_customer < len(row) else ""
        store = clean_val_str(row[idx_store]) if idx_store is not None and idx_store < len(row) else ""
        model_name = clean_val_str(row[idx_model]) if idx_model is not None and idx_model < len(row) else ""
        brand_name = clean_val_str(row[idx_brand]) if idx_brand is not None and idx_brand < len(row) else ""
        voucher_amt = clean_val_num(row[idx_voucher_amt]) if idx_voucher_amt is not None and idx_voucher_amt < len(row) else 0.0

        # ÇİFT KAYIT KONTROLÜ
        is_dup_in_file = raw_imei in seen_in_batch
        is_dup_in_db = raw_imei in existing_db_imeis

        if is_dup_in_file or is_dup_in_db:
            existing_info = existing_db_imeis.get(raw_imei, {})
            dup_reason = "Excel dosyası içinde mükerrer" if is_dup_in_file else f"Veritabanında zaten kayıtlı (Kayıt #{existing_info.get('id', '-')}, Mağaza: {existing_info.get('store_name', '-')})"
            
            skipped_duplicates.append({
                "row": row_index,
                "imei": raw_imei,
                "customer_name": cust_name,
                "model": model_name,
                "store_name": store,
                "voucher_amount": voucher_amt,
                "reason": dup_reason
            })

            if action_on_duplicate == "update" and is_dup_in_db:
                # İsteğe bağlı güncelleme
                cur.execute("""
                UPDATE mutabakat_records SET
                    customer_name = ?, store_name = ?, voucher_amount = ?, updated_at = CURRENT_TIMESTAMP
                WHERE imei = ?
                """, (cust_name, store, voucher_amt, raw_imei))
                updated_records.append(raw_imei)

            continue # ÇİFT KAYIT EKLENMEZ, ATLANIR

        seen_in_batch.add(raw_imei)

        # Diğer alanlar
        tc_val = clean_val_str(row[idx_tc]) if idx_tc is not None and idx_tc < len(row) else ""
        phone_val = clean_val_str(row[idx_phone]) if idx_phone is not None and idx_phone < len(row) else ""
        email_val = clean_val_str(row[idx_email]) if idx_email is not None and idx_email < len(row) else ""
        addr_val = clean_val_str(row[idx_address]) if idx_address is not None and idx_address < len(row) else ""
        prod_id_val = clean_val_str(row[idx_prod_id]) if idx_prod_id is not None and idx_prod_id < len(row) else ""
        status_val = clean_val_str(row[idx_status]) if idx_status is not None and idx_status < len(row) else ""
        delivered_val = clean_val_str(row[idx_delivered]) if idx_delivered is not None and idx_delivered < len(row) else ""
        deliv_date_val = clean_val_str(row[idx_deliv_date]) if idx_deliv_date is not None and idx_deliv_date < len(row) else ""
        track_val = clean_val_str(row[idx_track_no]) if idx_track_no is not None and idx_track_no < len(row) else ""
        cancel_val = clean_val_str(row[idx_cancel_reason]) if idx_cancel_reason is not None and idx_cancel_reason < len(row) else ""
        seq_val = clean_val_str(row[idx_seq]) if idx_seq is not None and idx_seq < len(row) else ""
        voucher_no_val = clean_val_str(row[idx_voucher_no]) if idx_voucher_no is not None and idx_voucher_no < len(row) else ""
        voucher_status_val = clean_val_str(row[idx_voucher_status]) if idx_voucher_status is not None and idx_voucher_status < len(row) else ""
        start_date_val = clean_val_str(row[idx_start_date]) if idx_start_date is not None and idx_start_date < len(row) else ""
        end_date_val = clean_val_str(row[idx_end_date]) if idx_end_date is not None and idx_end_date < len(row) else ""
        order_no_val = clean_val_str(row[idx_order_no]) if idx_order_no is not None and idx_order_no < len(row) else ""
        order_date_val = clean_val_str(row[idx_order_date]) if idx_order_date is not None and idx_order_date < len(row) else ""
        proc_start_val = clean_val_str(row[idx_proc_start]) if idx_proc_start is not None and idx_proc_start < len(row) else ""
        user_val = clean_val_str(row[idx_user]) if idx_user is not None and idx_user < len(row) else imported_by_user
        company_val = clean_val_str(row[idx_company]) if idx_company is not None and idx_company < len(row) else ""
        sent_val = clean_val_str(row[idx_sent]) if idx_sent is not None and idx_sent < len(row) else ""

        # Model Fiyat Eşleme & Formül Hesaplama
        model_clean = model_name.strip().lower()
        full_price = price_map.get(model_clean, 0.0)
        if full_price <= 0 and voucher_amt > 0:
            full_price = voucher_amt

        penalty_points = 0.0
        calculated_price = full_price # Henüz soru puanı girilmediğinden başlangıç hakediş = tam değer
        difference_amount = calculated_price - voucher_amt
        reconciliation_status = "Cevap bekleniyor"

        cur.execute(insert_sql, (
            cust_name, tc_val, phone_val, email_val, addr_val, prod_id_val, raw_imei, 0,
            brand_name, model_name, status_val, delivered_val, deliv_date_val, track_val, cancel_val,
            seq_val, voucher_no_val, voucher_amt, voucher_status_val, start_date_val, end_date_val,
            order_no_val, order_date_val, proc_start_val, user_val, store, company_val, sent_val,
            full_price, calculated_price, penalty_points, difference_amount, reconciliation_status,
            f"Günlük Excel Yüklemesi ile eklendi ({datetime.now().strftime('%d.%m.%Y %H:%M')})"
        ))

        existing_db_imeis[raw_imei] = {
            "id": cur.lastrowid,
            "store_name": store,
            "customer_name": cust_name
        }
        imported_records.append({
            "imei": raw_imei,
            "customer_name": cust_name,
            "model": model_name,
            "store_name": store,
            "voucher_amount": voucher_amt,
            "full_price": full_price,
            "difference_amount": difference_amount
        })

    conn.commit()
    conn.close()

    return {
        "success": True,
        "total_rows": row_index - 1,
        "imported_count": len(imported_records),
        "imported_records": imported_records,
        "skipped_duplicate_count": len(skipped_duplicates),
        "skipped_duplicates": skipped_duplicates,
        "updated_count": len(updated_records)
    }
