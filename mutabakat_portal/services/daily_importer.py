"""
Admin Günlük Excel Veri Yükleme, Ön Kontrol, Çift Kayıt Engelleme ve Toplu İşlemler Servisi
Destek / Günlük Gelen Excel Formatı (Destek Kasım Data.xlsx vb.)
"""
import openpyxl
import io
import re
import math
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
from ..database import get_connection
from .calculator import calculate_penalty_points, calculate_valuation


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


def parse_file_rows(file_bytes: bytes, filename: str = "") -> Tuple[Optional[List[Any]], Optional[List[List[Any]]], Optional[str]]:
    """CSV veya Excel dosyasını satır listesine dönüştürür."""
    header_row = None
    data_rows = []

    # CSV kontrolü
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
                    data_rows = csv_rows[1:]
                    break
            except Exception:
                continue

    # Excel kontrolü
    if header_row is None:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            header_row = list(next(rows_iter))
            data_rows = [list(r) for r in rows_iter if any(r)]
        except Exception as e:
            return None, None, f"Dosya açılamadı veya biçimi desteklenmiyor: {str(e)}"

    if not header_row:
        return None, None, "Dosya boş veya başlık satırı bulunamadı!"

    return header_row, data_rows, None


def map_columns(header_row: List[Any]) -> Dict[str, Optional[int]]:
    """Başlık satırını esnek Türkçe varyasyonlarla eşler."""
    col_map = {}
    for idx, h in enumerate(header_row):
        if not h:
            continue
        h_norm = normalize_header(str(h))
        col_map[h_norm] = idx

    def find_col(*aliases):
        for a in aliases:
            a_norm = normalize_header(a)
            if a_norm in col_map:
                return col_map[a_norm]
        return None

    return {
        "customer": find_col("MUSTERI", "MUSTERI_ADI_SOYADI", "AD_SOYAD", "CUSTOMER"),
        "tc": find_col("TCKN", "TC_NO", "TC_KIMLIK", "TC"),
        "phone": find_col("CEP_TELEFONU", "TELEFON", "PHONE", "MUSTERI_TELEFON"),
        "email": find_col("EMAIL", "E_POSTA", "E-MAIL"),
        "address": find_col("ADRES", "ADDRESS"),
        "prod_id": find_col("PRODUCT_ID", "URUN_ID", "PRODUCT"),
        "imei": find_col("IMEI", "SERI_NO", "SERIAL"),
        "brand": find_col("MARKA", "BRAND"),
        "model": find_col("MODEL"),
        "status": find_col("DURUM", "STATUS"),
        "delivered": find_col("TESLIM_EDILDI", "TESLIM_BILGISI", "DELIVERY"),
        "deliv_date": find_col("TESLIM_TARIHI", "DELIVERY_DATE"),
        "track_no": find_col("TAKIP_NUMARASI", "TRACKING_NO", "KARGO_TAKIP"),
        "cancel_reason": find_col("CANCEL_REASON", "IPTAL_NEDENI"),
        "seq": find_col("SEQ", "CEK_PREFIX", "PREFIX"),
        "voucher_no": find_col("CEK_PREFIX", "VOUCHER_NO", "CEK_NO", "SEQ"),
        "voucher_amt": find_col("BUYBACK_TUTARI", "CEK_TUTARI", "TUTAR", "AMOUNT"),
        "voucher_status": find_col("SEQ_STATUS", "CEK_DURUM"),
        "start_date": find_col("BASLANGIC_TARIHI", "START_DATE"),
        "end_date": find_col("BITIS_TARIHI", "END_DATE"),
        "order_no": find_col("SIPARIS_ID", "SIPARIS_NO", "ORDER_NO"),
        "order_date": find_col("SIPARIS_TARIHI", "ORDER_DATE"),
        "proc_start": find_col("ISLEM_BASLANGIC", "ISLEM_TARIHI"),
        "user": find_col("MUSTERI_TEMSILCISI", "ISLEMI_YAPAN", "USER"),
        "store": find_col("SIPARIS_MAGAZA", "MAGAZA", "MAGAZA_ADI", "STORE"),
        "company": find_col("FIRMA_ADI", "FIRMA", "COMPANY"),
        "sent": find_col("SENT")
    }


def preview_daily_excel(file_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """
    1. ADIM: Yüklenen dosyayı veritabanına yazmadan kontrol eder ve önizleme sunar.
    Mükerrerlikleri, model fiyat eşleşmelerini ve finansal hacmi raporlar.
    """
    header_row, data_rows, err = parse_file_rows(file_bytes, filename)
    if err:
        return {"success": False, "error": err}

    col_idx = map_columns(header_row)
    if col_idx["imei"] is None:
        return {"success": False, "error": "Dosyada zorunlu 'IMEI' sütunu bulunamadı!"}

    conn = get_connection()
    cur = conn.cursor()

    # Mevcut model tavan fiyatları
    cur.execute("SELECT LOWER(model_name), full_price FROM model_prices")
    price_map = {row[0].strip(): row[1] for row in cur.fetchall()}

    # Veritabanındaki tüm IMEI'ler
    cur.execute("SELECT imei, id, store_name, customer_name, reconciliation_status FROM mutabakat_records WHERE imei != ''")
    existing_db = {r["imei"].strip(): dict(r) for r in cur.fetchall()}
    conn.close()

    seen_in_file = set()
    new_rows = []
    duplicate_rows = []
    preview_samples = []
    total_voucher_sum = 0.0
    matched_models = 0

    for idx, row in enumerate(data_rows, start=2):
        if not any(row):
            continue

        raw_imei = clean_val_str(row[col_idx["imei"]] if col_idx["imei"] is not None and col_idx["imei"] < len(row) else "")
        if not raw_imei:
            continue

        cust_name = clean_val_str(row[col_idx["customer"]] if col_idx["customer"] is not None and col_idx["customer"] < len(row) else "")
        store_val = clean_val_str(row[col_idx["store"]] if col_idx["store"] is not None and col_idx["store"] < len(row) else "")
        model_val = clean_val_str(row[col_idx["model"]] if col_idx["model"] is not None and col_idx["model"] < len(row) else "")
        brand_val = clean_val_str(row[col_idx["brand"]] if col_idx["brand"] is not None and col_idx["brand"] < len(row) else "")
        voucher_amt = clean_val_num(row[col_idx["voucher_amt"]] if col_idx["voucher_amt"] is not None and col_idx["voucher_amt"] < len(row) else 0.0)

        total_voucher_sum += voucher_amt

        # Model eşleşme
        full_price = price_map.get(model_val.strip().lower(), 0.0)
        if full_price > 0:
            matched_models += 1
        elif voucher_amt > 0:
            full_price = voucher_amt

        # Mükerrer kontrolü
        is_dup_file = raw_imei in seen_in_file
        is_dup_db = raw_imei in existing_db

        item_info = {
            "row": idx,
            "imei": raw_imei,
            "customer_name": cust_name,
            "model": model_val,
            "brand": brand_val,
            "store_name": store_val,
            "voucher_amount": voucher_amt,
            "full_price": full_price,
            "status": "YENİ",
            "reason": ""
        }

        if is_dup_file or is_dup_db:
            if is_dup_file:
                item_info["status"] = "DOSYA İÇİ MÜKERRER"
                item_info["reason"] = "Aynı IMEI dosya içinde birden fazla satırda geçiyor"
            else:
                db_info = existing_db[raw_imei]
                item_info["status"] = "VERİTABANINDA MEVCUT"
                item_info["reason"] = f"DB Kayıt #{db_info['id']} ({db_info.get('store_name', '-')}) ile mükerrer"
            duplicate_rows.append(item_info)
        else:
            seen_in_file.add(raw_imei)
            new_rows.append(item_info)

        if len(preview_samples) < 12:
            preview_samples.append(item_info)

    return {
        "success": True,
        "filename": filename,
        "file_size_kb": round(len(file_bytes) / 1024, 1),
        "total_rows": len(data_rows),
        "valid_count": len(new_rows) + len(duplicate_rows),
        "new_count": len(new_rows),
        "duplicate_count": len(duplicate_rows),
        "matched_models": matched_models,
        "total_voucher_sum": total_voucher_sum,
        "preview_samples": preview_samples,
        "duplicates": duplicate_rows
    }


def import_daily_excel(
    file_bytes: bytes,
    filename: str = "",
    action_on_duplicate: str = "skip", # "skip" veya "update"
    imported_by_user: str = "admin"
) -> Dict[str, Any]:
    """
    2. ADIM: Kontrol edilmiş günlük veriyi içe aktarır ve import_batches tablosuna kaydeder.
    """
    header_row, data_rows, err = parse_file_rows(file_bytes, filename)
    if err:
        return {"success": False, "error": err}

    col_idx = map_columns(header_row)
    if col_idx["imei"] is None:
        return {"success": False, "error": "Excel tablosunda 'IMEI' sütunu bulunamadı!"}

    # Benzersiz batch ID oluştur
    batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT LOWER(model_name), full_price FROM model_prices")
    price_map = {row[0].strip(): row[1] for row in cur.fetchall()}

    cur.execute("SELECT imei, id, store_name, customer_name FROM mutabakat_records WHERE imei != ''")
    existing_db = {r["imei"].strip(): dict(r) for r in cur.fetchall()}

    seen_in_batch = set()
    imported_records = []
    skipped_duplicates = []
    updated_records = []
    total_voucher_sum = 0.0

    insert_sql = """
    INSERT INTO mutabakat_records (
        customer_name, tc_no, phone, email, address, product_id, imei, is_duplicate,
        brand, model, status, delivery_info, delivery_date, tracking_no, cancel_reason,
        voucher_prefix, voucher_no, voucher_amount, voucher_status, start_date, end_date,
        order_no, order_date, process_start_date, process_user, store_name, company_name, sent,
        full_price, calculated_price, penalty_points, difference_amount, reconciliation_status,
        notes, import_batch_id
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?
    )
    """

    for idx, row in enumerate(data_rows, start=2):
        if not any(row):
            continue

        raw_imei = clean_val_str(row[col_idx["imei"]] if col_idx["imei"] is not None and col_idx["imei"] < len(row) else "")
        if not raw_imei:
            continue

        cust_name = clean_val_str(row[col_idx["customer"]] if col_idx["customer"] is not None and col_idx["customer"] < len(row) else "")
        store = clean_val_str(row[col_idx["store"]] if col_idx["store"] is not None and col_idx["store"] < len(row) else "")
        model_name = clean_val_str(row[col_idx["model"]] if col_idx["model"] is not None and col_idx["model"] < len(row) else "")
        brand_name = clean_val_str(row[col_idx["brand"]] if col_idx["brand"] is not None and col_idx["brand"] < len(row) else "")
        voucher_amt = clean_val_num(row[col_idx["voucher_amt"]] if col_idx["voucher_amt"] is not None and col_idx["voucher_amt"] < len(row) else 0.0)

        # Çift Kayıt Kontrolü
        is_dup_file = raw_imei in seen_in_batch
        is_dup_db = raw_imei in existing_db

        if is_dup_file or is_dup_db:
            existing_info = existing_db.get(raw_imei, {})
            dup_reason = "Excel dosyası içinde mükerrer" if is_dup_file else f"Veritabanında kayıtlı (Kayıt #{existing_info.get('id', '-')})"
            skipped_duplicates.append({
                "row": idx,
                "imei": raw_imei,
                "customer_name": cust_name,
                "model": model_name,
                "store_name": store,
                "voucher_amount": voucher_amt,
                "reason": dup_reason
            })

            if action_on_duplicate == "update" and is_dup_db:
                # Mevcut kaydı güncelle ve batch_id ata
                cur.execute("""
                UPDATE mutabakat_records SET
                    customer_name = ?, store_name = ?, voucher_amount = ?,
                    import_batch_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE imei = ?
                """, (cust_name, store, voucher_amt, batch_id, raw_imei))
                updated_records.append(raw_imei)

            continue

        seen_in_batch.add(raw_imei)
        total_voucher_sum += voucher_amt

        tc_val = clean_val_str(row[col_idx["tc"]] if col_idx["tc"] is not None and col_idx["tc"] < len(row) else "")
        phone_val = clean_val_str(row[col_idx["phone"]] if col_idx["phone"] is not None and col_idx["phone"] < len(row) else "")
        email_val = clean_val_str(row[col_idx["email"]] if col_idx["email"] is not None and col_idx["email"] < len(row) else "")
        addr_val = clean_val_str(row[col_idx["address"]] if col_idx["address"] is not None and col_idx["address"] < len(row) else "")
        prod_id_val = clean_val_str(row[col_idx["prod_id"]] if col_idx["prod_id"] is not None and col_idx["prod_id"] < len(row) else "")
        status_val = clean_val_str(row[col_idx["status"]] if col_idx["status"] is not None and col_idx["status"] < len(row) else "")
        delivered_val = clean_val_str(row[col_idx["delivered"]] if col_idx["delivered"] is not None and col_idx["delivered"] < len(row) else "")
        deliv_date_val = clean_val_str(row[col_idx["deliv_date"]] if col_idx["deliv_date"] is not None and col_idx["deliv_date"] < len(row) else "")
        track_val = clean_val_str(row[col_idx["track_no"]] if col_idx["track_no"] is not None and col_idx["track_no"] < len(row) else "")
        cancel_val = clean_val_str(row[col_idx["cancel_reason"]] if col_idx["cancel_reason"] is not None and col_idx["cancel_reason"] < len(row) else "")
        seq_val = clean_val_str(row[col_idx["seq"]] if col_idx["seq"] is not None and col_idx["seq"] < len(row) else "")
        voucher_no_val = clean_val_str(row[col_idx["voucher_no"]] if col_idx["voucher_no"] is not None and col_idx["voucher_no"] < len(row) else "")
        voucher_status_val = clean_val_str(row[col_idx["voucher_status"]] if col_idx["voucher_status"] is not None and col_idx["voucher_status"] < len(row) else "")
        start_date_val = clean_val_str(row[col_idx["start_date"]] if col_idx["start_date"] is not None and col_idx["start_date"] < len(row) else "")
        end_date_val = clean_val_str(row[col_idx["end_date"]] if col_idx["end_date"] is not None and col_idx["end_date"] < len(row) else "")
        order_no_val = clean_val_str(row[col_idx["order_no"]] if col_idx["order_no"] is not None and col_idx["order_no"] < len(row) else "")
        order_date_val = clean_val_str(row[col_idx["order_date"]] if col_idx["order_date"] is not None and col_idx["order_date"] < len(row) else "")
        proc_start_val = clean_val_str(row[col_idx["proc_start"]] if col_idx["proc_start"] is not None and col_idx["proc_start"] < len(row) else "")
        user_val = clean_val_str(row[col_idx["user"]] if col_idx["user"] is not None and col_idx["user"] < len(row) else imported_by_user)
        company_val = clean_val_str(row[col_idx["company"]] if col_idx["company"] is not None and col_idx["company"] < len(row) else "")
        sent_val = clean_val_str(row[col_idx["sent"]] if col_idx["sent"] is not None and col_idx["sent"] < len(row) else "")

        model_clean = model_name.strip().lower()
        full_price = price_map.get(model_clean, 0.0)
        if full_price <= 0 and voucher_amt > 0:
            full_price = voucher_amt

        penalty_points = 0.0
        calculated_price = full_price
        difference_amount = calculated_price - voucher_amt
        reconciliation_status = "Cevap bekleniyor"

        cur.execute(insert_sql, (
            cust_name, tc_val, phone_val, email_val, addr_val, prod_id_val, raw_imei, 0,
            brand_name, model_name, status_val, delivered_val, deliv_date_val, track_val, cancel_val,
            seq_val, voucher_no_val, voucher_amt, voucher_status_val, start_date_val, end_date_val,
            order_no_val, order_date_val, proc_start_val, user_val, store, company_val, sent_val,
            full_price, calculated_price, penalty_points, difference_amount, reconciliation_status,
            f"Günlük Excel Yüklemesi ile eklendi ({datetime.now().strftime('%d.%m.%Y %H:%M')})",
            batch_id
        ))

        imported_records.append({
            "imei": raw_imei,
            "customer_name": cust_name,
            "model": model_name,
            "store_name": store,
            "voucher_amount": voucher_amt,
            "full_price": full_price,
            "difference_amount": difference_amount
        })

    # Paket geçmişine kaydet
    cur.execute("""
    INSERT INTO import_batches (
        batch_id, filename, file_size, total_rows, imported_count, skipped_count,
        updated_count, total_voucher, imported_by, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    """, (
        batch_id, filename, len(file_bytes), len(data_rows), len(imported_records),
        len(skipped_duplicates), len(updated_records), total_voucher_sum, imported_by_user
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "batch_id": batch_id,
        "filename": filename,
        "total_rows": len(data_rows),
        "imported_count": len(imported_records),
        "imported_records": imported_records[:20],
        "skipped_duplicate_count": len(skipped_duplicates),
        "skipped_duplicates": skipped_duplicates,
        "updated_count": len(updated_records),
        "total_voucher_sum": total_voucher_sum
    }


def get_last_active_batch() -> Optional[Dict[str, Any]]:
    """En son yapılan ve henüz geri alınmamış aktarım paketini getirir."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM import_batches WHERE status = 'active' ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_batches(limit: int = 15) -> List[Dict[str, Any]]:
    """Son aktarım paketlerini listeler."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM import_batches ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revert_last_import(reverted_by: str = "admin") -> Dict[str, Any]:
    """En son yapılan aktarımı geri alır ve eklenen kayıtları veritabanından siler."""
    batch = get_last_active_batch()
    if not batch:
        return {"success": False, "error": "Geri alınabilecek aktif bir içe aktarım paketi bulunamadı!"}

    return revert_batch_by_id(batch["batch_id"], reverted_by=reverted_by)


def revert_batch_by_id(batch_id: str, reverted_by: str = "admin") -> Dict[str, Any]:
    """Belirli bir aktarım paketini ID'sine göre geri alır ve kayıtları siler."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM import_batches WHERE batch_id = ?", (batch_id,))
    batch = cur.fetchone()
    if not batch:
        conn.close()
        return {"success": False, "error": f"'{batch_id}' kimlikli aktarım paketi bulunamadı!"}

    cur.execute("SELECT COUNT(*) as c FROM mutabakat_records WHERE import_batch_id = ?", (batch_id,))
    count_to_delete = cur.fetchone()["c"]

    # Kayıtları sil
    cur.execute("DELETE FROM mutabakat_records WHERE import_batch_id = ?", (batch_id,))
    # Paketi iptal olarak işaretle
    cur.execute("UPDATE import_batches SET status = 'reverted', reverted_at = CURRENT_TIMESTAMP WHERE batch_id = ?", (batch_id,))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "batch_id": batch_id,
        "filename": batch["filename"],
        "deleted_count": count_to_delete,
        "message": f"'{batch['filename']}' ({batch_id}) paketindeki {count_to_delete} adet cihaz kaydı başarıyla silindi ve aktarım geri alındı."
    }


def recalculate_all_records() -> Dict[str, Any]:
    """
    Tüm veritabanındaki hakediş, soru puanları ve fark hesaplarını güncel model fiyatlarına göre yeniden hesaplar.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT LOWER(model_name), full_price FROM model_prices")
    price_map = {row[0].strip(): row[1] for row in cur.fetchall()}

    cur.execute("""
    SELECT id, model, full_price, voucher_amount,
           q1_working, q2_btk, q3_home_faceid, q4_icloud,
           q5_apple_body, q6_apple_screen, q7_apple_camera, q8_apple_battery,
           q5_android_camera, q6_android_body, q7_android_screen
    FROM mutabakat_records
    """)
    records = cur.fetchall()

    updated_count = 0
    for r in records:
        answers = {
            "q1_working": r["q1_working"] or "",
            "q2_btk": r["q2_btk"] or "",
            "q3_home_faceid": r["q3_home_faceid"] or "",
            "q4_icloud": r["q4_icloud"] or "",
            "q5_apple_body": r["q5_apple_body"] or "",
            "q6_apple_screen": r["q6_apple_screen"] or "",
            "q7_apple_camera": r["q7_apple_camera"] or "",
            "q8_apple_battery": r["q8_apple_battery"] or "",
            "q5_android_camera": r["q5_android_camera"] or "",
            "q6_android_body": r["q6_android_body"] or "",
            "q7_android_screen": r["q7_android_screen"] or ""
        }

        model_clean = (r["model"] or "").strip().lower()
        full_price = price_map.get(model_clean, r["full_price"] or 0.0)
        if full_price <= 0 and r["voucher_amount"] > 0:
            full_price = r["voucher_amount"]

        penalty = calculate_penalty_points(answers)
        calc_price, diff = calculate_valuation(full_price, penalty, r["voucher_amount"] or 0.0)

        cur.execute("""
        UPDATE mutabakat_records SET
            full_price = ?, penalty_points = ?, calculated_price = ?, difference_amount = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (full_price, penalty, calc_price, diff, r["id"]))
        updated_count += 1

    conn.commit()
    conn.close()

    return {
        "success": True,
        "updated_count": updated_count,
        "message": f"Tüm veritabanı başarıyla güncellendi: {updated_count:,} adet cihazın hakediş ve mutabakat farkları yeniden hesaplandı."
    }


def search_imeis_for_deletion(imeis_input: str) -> Dict[str, Any]:
    """Girilen IMEI / seri no metnini ayrıştırır ve veritabanında eşleşen kayıtları bulur."""
    tokens = [t.strip() for t in re.split(r'[\r\n,;\t ]+', imeis_input) if t.strip()]
    unique_tokens = list(dict.fromkeys(tokens))

    if not unique_tokens:
        return {"success": False, "error": "Lütfen en az bir IMEI veya Seri No girin!"}

    conn = get_connection()
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(unique_tokens))
    cur.execute(f"""
    SELECT id, imei, customer_name, model, brand, store_name, process_user,
           voucher_amount, calculated_price, difference_amount, reconciliation_status,
           process_start_date, import_batch_id
    FROM mutabakat_records
    WHERE imei IN ({placeholders})
    ORDER BY id DESC
    """, tuple(unique_tokens))

    matches = [dict(r) for r in cur.fetchall()]
    conn.close()

    matched_imeis = set(m["imei"].strip() for m in matches)
    not_found = [tok for tok in unique_tokens if tok not in matched_imeis]

    return {
        "success": True,
        "total_searched": len(unique_tokens),
        "matched_count": len(matches),
        "not_found_count": len(not_found),
        "matches": matches,
        "not_found": not_found
    }


def delete_records_by_ids(record_ids: List[int]) -> int:
    """Verilen kayıt ID'lerini veritabanından kalıcı olarak siler."""
    if not record_ids:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(record_ids))
    cur.execute(f"DELETE FROM mutabakat_records WHERE id IN ({placeholders})", tuple(record_ids))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted

