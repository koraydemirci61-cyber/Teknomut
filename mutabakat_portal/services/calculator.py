"""
Teknosa Buyback & Mutabakat Formül ve Hesaplama Motoru
Excel tablosundaki formüllerin ve dinamik veritabanı kural motorunun Python uygulamasıdır:
1. Eksi Puan: Sorulara verilen cevaplara göre toplam ceza/hasar kesinti yüzdesi (AT Sütunu)
2. Fiyat (Hakediş): ROUNDUP(IF(AT > 90, AU/100*10, AU/100*(100-AT)), 0) (AS Sütunu)
3. Fark: FİYAT - Çek Tutarı (AV Sütunu)
4. Çift Adet Kontrolü: COUNTIF(G:G, G) (H Sütunu)
"""
import math
import json
import re
from typing import Dict, Any, Optional, Tuple, List
from ..database import get_connection, query_all, query_one, execute_db


QUESTIONS_DEF = [
    {
        "id": "q1_working",
        "code": "q1_working",
        "title": "1. Cihaz çalışır durumdadır ve bataryası mevcuttur",
        "type": "bool_penalty",
        "device_group": "ALL",
        "options": [
            {"val": "", "label": "Sorun Yok / Çalışıyor", "penalty": 0},
            {"val": "Y", "label": "Çalışmıyor / Batarya Yok", "penalty": 100}
        ]
    },
    {
        "id": "q2_btk",
        "code": "q2_btk",
        "title": "2. Cihazın BTK sorgusu temizdir (Çalıntı, klon veya pasaport kayıtlı DEĞİL)",
        "type": "bool_penalty",
        "device_group": "ALL",
        "options": [
            {"val": "", "label": "Temiz / Sorun Yok", "penalty": 0},
            {"val": "Y", "label": "Sorunlu / Klon / Çalıntı", "penalty": 100}
        ]
    },
    {
        "id": "q3_home_faceid",
        "code": "q3_home_faceid",
        "title": "3. Home tuşu, Parmak İzi veya Face ID çalışıyor mu?",
        "type": "bool_penalty",
        "device_group": "ALL",
        "options": [
            {"val": "", "label": "Çalışıyor", "penalty": 0},
            {"val": "Y", "label": "Çalışmıyor / Arızalı", "penalty": 40}
        ]
    },
    {
        "id": "q4_icloud",
        "code": "q4_icloud",
        "title": "4. Cihaz sıfırlandı, iCloud / Google hesap kaldırıldı",
        "type": "bool_penalty",
        "device_group": "ALL",
        "options": [
            {"val": "", "label": "Sıfırlandı / Kilit Açık", "penalty": 0},
            {"val": "Y", "label": "Kilitli / Hesap Kaldırılmadı", "penalty": 70}
        ]
    },
    # Apple Soruları
    {
        "id": "q5_apple_body",
        "code": "q5_apple_body",
        "title": "5. (Apple) Kasa Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Temiz / Hasarsız", "penalty": 0},
            {"val": "D", "label": "Çizik / Boya Soyulması", "penalty": 10},
            {"val": "Y", "label": "Çatlak / Kırık / Kasa Açık", "penalty": 15}
        ]
    },
    {
        "id": "q6_apple_screen",
        "code": "q6_apple_screen",
        "title": "6. (Apple) Ekran Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Kusursuz", "penalty": 0},
            {"val": "D", "label": "Çizik", "penalty": 15},
            {"val": "Y", "label": "Kırık / Leke / Sararma / Yanma / Bilinmeyen Parça", "penalty": 40}
        ]
    },
    {
        "id": "q7_apple_camera",
        "code": "q7_apple_camera",
        "title": "7. (Apple) Kamera Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Temiz", "penalty": 0},
            {"val": "D", "label": "Leke / Renk Değişimi", "penalty": 15},
            {"val": "Y", "label": "Bilinmeyen Parça / Arızalı", "penalty": 25}
        ]
    },
    {
        "id": "q8_apple_battery",
        "code": "q8_apple_battery",
        "title": "8. (Apple) Pil Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Sağlıklı (Pil >= %85)", "penalty": 0},
            {"val": "D", "label": "Pil Sağlığı %85 Altında", "penalty": 15},
            {"val": "Y", "label": "Bilinmeyen Parça / Şişik", "penalty": 25}
        ]
    },
    # Android Soruları
    {
        "id": "q5_android_camera",
        "code": "q5_android_camera",
        "title": "5. (Android) Kamera Durumu",
        "type": "bool_penalty",
        "device_group": "ANDROID",
        "options": [
            {"val": "", "label": "Leke / Kusur Yok", "penalty": 0},
            {"val": "Y", "label": "Görüntüde Leke / Renk Değişimi Var", "penalty": 40}
        ]
    },
    {
        "id": "q6_android_body",
        "code": "q6_android_body",
        "title": "6. (Android) Kasa Durumu",
        "type": "multi_penalty",
        "device_group": "ANDROID",
        "options": [
            {"val": "", "label": "Temiz", "penalty": 0},
            {"val": "D", "label": "Çizik / Boya Soyulması", "penalty": 15},
            {"val": "Y", "label": "Çatlak / Kırık / Kasa Açık", "penalty": 20}
        ]
    },
    {
        "id": "q7_android_screen",
        "code": "q7_android_screen",
        "title": "7. (Android) Ekran Durumu",
        "type": "multi_penalty",
        "device_group": "ANDROID",
        "options": [
            {"val": "", "label": "Kusursuz", "penalty": 0},
            {"val": "D", "label": "Çizik", "penalty": 20},
            {"val": "Y", "label": "Kırık / Leke / Sararma / Hayalet Ekran", "penalty": 40}
        ]
    }
]


def get_all_questions(include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Veritabanından hasar ve fonksiyon sorgu maddelerini getirir."""
    try:
        where_sql = "" if include_inactive else "WHERE is_active = 1"
        rows = query_all(f"SELECT * FROM inspection_questions {where_sql} ORDER BY order_num ASC, id ASC")
        if not rows:
            return QUESTIONS_DEF
        
        result = []
        for r in rows:
            q = dict(r)
            q["id"] = q["code"] # Form şablonu id/name uyumu için
            try:
                q["options"] = json.loads(q["options_json"])
            except Exception:
                q["options"] = []
            result.append(q)
        return result
    except Exception:
        return QUESTIONS_DEF


def get_question_by_id(question_id: int) -> Optional[Dict[str, Any]]:
    """ID'ye göre tekil soru maddesini getirir."""
    row = query_one("SELECT * FROM inspection_questions WHERE id = ?", (question_id,))
    if not row:
        return None
    q = dict(row)
    q["id_num"] = q["id"]
    q["id"] = q["code"]
    try:
        q["options"] = json.loads(q["options_json"])
    except Exception:
        q["options"] = []
    return q


def add_question(
    title: str,
    device_group: str,
    options: List[Dict[str, Any]],
    code: Optional[str] = None,
    order_num: int = 0
) -> Dict[str, Any]:
    """Yeni hasar/fonksiyon soru maddesi ekler ve gerekiyorsa mutabakat_records tablosuna sütun açar."""
    clean_title = title.strip()
    if not clean_title:
        return {"success": False, "error": "Soru başlığı boş bırakılamaz."}

    if not code or not code.strip():
        # Otomatik kod üret: q_ses, q_sarj vb.
        slug = re.sub(r"[^a-zA-Z0-9_]", "", clean_title.lower().replace(" ", "_"))[:15]
        code = f"q_{slug}" if slug else f"q_custom_{order_num}"

    clean_code = re.sub(r"[^a-zA-Z0-9_]", "", code.strip().lower())
    if not clean_code:
        return {"success": False, "error": "Geçerli bir soru kodu girilmelidir."}

    # Kod çakışması kontrolü
    existing = query_one("SELECT id FROM inspection_questions WHERE LOWER(code) = LOWER(?)", (clean_code,))
    if existing:
        return {"success": False, "error": f"'{clean_code}' kodu zaten mevcut! Farklı bir kod belirleyin."}

    if device_group not in ("ALL", "APPLE", "ANDROID"):
        device_group = "ALL"

    # mutabakat_records tablosunda sütun yoksa otomatik ekle
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(mutabakat_records)")
        existing_cols = set(r["name"] for r in cur.fetchall())
        if clean_code not in existing_cols:
            cur.execute(f"ALTER TABLE mutabakat_records ADD COLUMN {clean_code} TEXT;")
        
        opt_json = json.dumps(options, ensure_ascii=False)
        cur.execute("""
        INSERT INTO inspection_questions (code, title, device_group, question_type, options_json, order_num, is_active)
        VALUES (?, ?, ?, 'multi', ?, ?, 1)
        """, (clean_code, clean_title, device_group, opt_json, order_num))
        conn.commit()
        return {"success": True, "message": f"'{clean_title}' soru maddesi başarıyla eklendi.", "code": clean_code}
    except Exception as e:
        return {"success": False, "error": f"Veritabanı hatası: {str(e)}"}
    finally:
        conn.close()


def update_question(
    question_id: int,
    title: str,
    device_group: str,
    options: List[Dict[str, Any]],
    order_num: int = 0
) -> Dict[str, Any]:
    """Mevcut soru maddesini ve ceza puanlarını günceller."""
    clean_title = title.strip()
    if not clean_title:
        return {"success": False, "error": "Soru başlığı boş bırakılamaz."}

    if device_group not in ("ALL", "APPLE", "ANDROID"):
        device_group = "ALL"

    opt_json = json.dumps(options, ensure_ascii=False)
    execute_db("""
    UPDATE inspection_questions SET
        title = ?, device_group = ?, options_json = ?, order_num = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (clean_title, device_group, opt_json, order_num, question_id))

    return {"success": True, "message": f"'{clean_title}' soru maddesi ve ceza puanları güncellendi."}


def toggle_question_status(question_id: int) -> Dict[str, Any]:
    """Soru maddesini aktif veya pasif (çıkartılmış) yapar."""
    q = query_one("SELECT * FROM inspection_questions WHERE id = ?", (question_id,))
    if not q:
        return {"success": False, "error": "Soru maddesi bulunamadı."}

    new_status = 0 if q["is_active"] else 1
    execute_db("UPDATE inspection_questions SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, question_id))
    durum = "aktifleştirildi" if new_status == 1 else "çıkartıldı (pasife alındı)"
    return {"success": True, "message": f"'{q['title']}' maddesi {durum}."}


def delete_question(question_id: int) -> Dict[str, Any]:
    """Soru maddesini veritabanından kalıcı olarak siler."""
    q = query_one("SELECT * FROM inspection_questions WHERE id = ?", (question_id,))
    if not q:
        return {"success": False, "error": "Soru maddesi bulunamadı."}

    execute_db("DELETE FROM inspection_questions WHERE id = ?", (question_id,))
    return {"success": True, "message": f"'{q['title']}' soru maddesi sistemden silindi."}


def calculate_penalty_points(
    answers: Dict[str, Any],
    questions: Optional[List[Dict[str, Any]]] = None,
    brand: str = ""
) -> float:
    """
    Dinamik Soru Setine Göre Toplam Eksi Puanı (AT Sütunu) Hesaplar.
    Her soru için verilen cevaba karşılık gelen %lik ceza puanını toplar.
    """
    if questions is None:
        questions = get_all_questions(include_inactive=False)

    penalty = 0.0
    brand_upper = (brand or "").strip().upper()

    for q in questions:
        q_code = q.get("code") or q.get("id")
        q_group = (q.get("device_group") or "ALL").upper()

        # Markaya özel soru filtreleme
        if brand_upper:
            if brand_upper == "APPLE" and q_group == "ANDROID":
                continue
            if brand_upper != "APPLE" and q_group == "APPLE":
                continue

        val = answers.get(q_code)
        if val is None or val == "":
            continue

        val_str = str(val).strip()

        # Seçenekler içinden eşleşen ceza puanını bul
        for opt in q.get("options", []):
            if str(opt.get("val", "")).strip() == val_str:
                penalty += float(opt.get("penalty", 0.0))
                break

    return penalty


def calculate_valuation(full_price: float, penalty_points: float, voucher_amount: float) -> Tuple[float, float]:
    """
    Excel Formülü:
    FİYAT (AS): =ROUNDUP(IF(AT > 90, AU/100*10, AU/100*(100-AT)), 0)
    Fark (AV):  =AS - U
    """
    if full_price <= 0:
        return 0.0, 0.0 - voucher_amount

    if penalty_points > 90.0:
        raw_price = (full_price / 100.0) * 10.0
    else:
        remaining_ratio = max(0.0, 100.0 - penalty_points)
        raw_price = (full_price / 100.0) * remaining_ratio

    calculated_price = float(math.ceil(raw_price))
    difference_amount = calculated_price - voucher_amount
    return calculated_price, difference_amount

