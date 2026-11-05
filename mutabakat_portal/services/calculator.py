"""
Teknosa Buyback & Mutabakat Formül ve Hesaplama Motoru
Excel tablosundaki formüllerin birebir Python uygulamasıdır:
1. Eksi Puan: Sorulara verilen cevaplara göre toplam ceza/hasar kesinti yüzdesi (AT Sütunu)
2. Fiyat (Hakediş): ROUNDUP(IF(AT > 90, AU/100*10, AU/100*(100-AT)), 0) (AS Sütunu)
3. Fark: FİYAT - Çek Tutarı (AV Sütunu)
4. Çift Adet Kontrolü: COUNTIF(G:G, G) (H Sütunu)
"""
import math
from typing import Dict, Any, Optional, Tuple


QUESTIONS_DEF = [
    {
        "id": "q1_working",
        "title": "1. Cihaz çalışır durumdadır ve bataryası mevcuttur",
        "type": "bool_penalty",
        "penalty_val": 100,
        "options": [
            {"val": "", "label": "Sorun Yok / Çalışıyor (0 Ceza)"},
            {"val": "Y", "label": "Çalışmıyor / Batarya Yok (-100 Puan)"}
        ]
    },
    {
        "id": "q2_btk",
        "title": "2. Cihazın BTK sorgusu temizdir (Çalıntı, klon veya pasaport kayıtlı DEĞİL)",
        "type": "bool_penalty",
        "penalty_val": 100,
        "options": [
            {"val": "", "label": "Temiz / Sorun Yok (0 Ceza)"},
            {"val": "Y", "label": "Sorunlu / Klon / Çalıntı (-100 Puan)"}
        ]
    },
    {
        "id": "q3_home_faceid",
        "title": "3. Home tuşu, Parmak İzi veya Face ID çalışıyor mu?",
        "type": "bool_penalty",
        "penalty_val": 40,
        "options": [
            {"val": "", "label": "Çalışıyor (0 Ceza)"},
            {"val": "Y", "label": "Çalışmıyor / Arızalı (-40 Puan)"}
        ]
    },
    {
        "id": "q4_icloud",
        "title": "4. Cihaz sıfırlandı, iCloud / Google hesap kaldırıldı",
        "type": "bool_penalty",
        "penalty_val": 70,
        "options": [
            {"val": "", "label": "Sıfırlandı / Kilit Açık (0 Ceza)"},
            {"val": "Y", "label": "Kilitli / Hesap Kaldırılmadı (-70 Puan)"}
        ]
    },
    # Apple Soruları
    {
        "id": "q5_apple_body",
        "title": "5. (Apple) Kasa Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Temiz / Hasarsız (0 Ceza)"},
            {"val": "D", "label": "Çizik / Boya Soyulması (-10 Puan)"},
            {"val": "Y", "label": "Çatlak / Kırık / Kasa Açık (-15 Puan)"}
        ]
    },
    {
        "id": "q6_apple_screen",
        "title": "6. (Apple) Ekran Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Kusursuz (0 Ceza)"},
            {"val": "D", "label": "Çizik (-15 Puan)"},
            {"val": "Y", "label": "Kırık / Leke / Sararma / Yanma / Bilinmeyen Parça (-40 Puan)"}
        ]
    },
    {
        "id": "q7_apple_camera",
        "title": "7. (Apple) Kamera Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Temiz (0 Ceza)"},
            {"val": "D", "label": "Leke / Renk Değişimi (-15 Puan)"},
            {"val": "Y", "label": "Bilinmeyen Parça / Arızalı (-25 Puan)"}
        ]
    },
    {
        "id": "q8_apple_battery",
        "title": "8. (Apple) Pil Durumu",
        "type": "multi_penalty",
        "device_group": "APPLE",
        "options": [
            {"val": "", "label": "Sağlıklı (Pil >= %85) (0 Ceza)"},
            {"val": "D", "label": "Pil Sağlığı %85 Altında (-15 Puan)"},
            {"val": "Y", "label": "Bilinmeyen Parça / Şişik (-25 Puan)"}
        ]
    },
    # Android Soruları
    {
        "id": "q5_android_camera",
        "title": "5. (Android) Kamera Durumu",
        "type": "bool_penalty",
        "device_group": "ANDROID",
        "penalty_val": 40,
        "options": [
            {"val": "", "label": "Leke / Kusur Yok (0 Ceza)"},
            {"val": "Y", "label": "Görüntüde Leke / Renk Değişimi Var (-40 Puan)"}
        ]
    },
    {
        "id": "q6_android_body",
        "title": "6. (Android) Kasa Durumu",
        "type": "multi_penalty",
        "device_group": "ANDROID",
        "options": [
            {"val": "", "label": "Temiz (0 Ceza)"},
            {"val": "D", "label": "Çizik / Boya Soyulması (-15 Puan)"},
            {"val": "Y", "label": "Çatlak / Kırık / Kasa Açık (-20 Puan)"}
        ]
    },
    {
        "id": "q7_android_screen",
        "title": "7. (Android) Ekran Durumu",
        "type": "multi_penalty",
        "device_group": "ANDROID",
        "options": [
            {"val": "", "label": "Kusursuz (0 Ceza)"},
            {"val": "D", "label": "Çizik (-20 Puan)"},
            {"val": "Y", "label": "Kırık / Leke / Sararma / Hayalet Ekran (-40 Puan)"}
        ]
    }
]


def calculate_penalty_points(answers: Dict[str, str]) -> float:
    """
    Excel Formülü (AT Sütunu):
    =IF(AI="Y",100,0)+IF(AH="Y",100,0)+IF(AJ="Y",40,0)+IF(AK="Y",70,0)
     +IF(AL="Y",15,0)+IF(AL="D",10,0)
     +IF(AM="D",15,0)+IF(AM="Y",40,0)
     +IF(AN="Y",25,0)+IF(AN="D",15,0)
     +IF(AO="Y",25,0)+IF(AO="D",15,0)
     +IF(AP="Y",40,0)
     +IF(AQ="Y",20,0)+IF(AQ="D",15,0)
     +IF(AR="Y",40,0)+IF(AR="D",20,0)
    """
    penalty = 0.0

    # q1 (AH)
    if answers.get("q1_working") == "Y":
        penalty += 100.0
    # q2 (AI)
    if answers.get("q2_btk") == "Y":
        penalty += 100.0
    # q3 (AJ)
    if answers.get("q3_home_faceid") == "Y":
        penalty += 40.0
    # q4 (AK)
    if answers.get("q4_icloud") == "Y":
        penalty += 70.0

    # Apple (AL, AM, AN, AO)
    al = answers.get("q5_apple_body", "")
    if al == "Y":
        penalty += 15.0
    elif al == "D":
        penalty += 10.0

    am = answers.get("q6_apple_screen", "")
    if am == "Y":
        penalty += 40.0
    elif am == "D":
        penalty += 15.0

    an = answers.get("q7_apple_camera", "")
    if an == "Y":
        penalty += 25.0
    elif an == "D":
        penalty += 15.0

    ao = answers.get("q8_apple_battery", "")
    if ao == "Y":
        penalty += 25.0
    elif ao == "D":
        penalty += 15.0

    # Android (AP, AQ, AR)
    if answers.get("q5_android_camera") == "Y":
        penalty += 40.0

    aq = answers.get("q6_android_body", "")
    if aq == "Y":
        penalty += 20.0
    elif aq == "D":
        penalty += 15.0

    ar = answers.get("q7_android_screen", "")
    if ar == "Y":
        penalty += 40.0
    elif ar == "D":
        penalty += 20.0

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
