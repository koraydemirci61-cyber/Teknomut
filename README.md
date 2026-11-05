# Teknosa Buyback Mutabakat ve Hakediş Yönetim Portalı

Teknosa mağazalarından geri alınan (Buyback) ikinci el cihazların ekspertiz kontrollerini, hasar ve fonksiyon test puanlarını, liste tavan değerlerini ve çek tutarı mutabakatlarını yöneten online web portalı.

## 🚀 Özellikler

1. **Dashboard & Finansal Analitik:**
   - Toplam işlem sayısı, verilen hediye çeki tutarı, hesaplanan hakediş tutarı ve mutabakat farkı.
   - Mutabakat statü dağılımı (Tamamlandı, Cevap Bekleniyor, İptal) ve marka bazlı pasta/çubuk grafikleri.
   - Riskli fark / uyuşmazlık tablosu.

2. **Günlük Excel / CSV Toplu Veri Yükleme (Admin):**
   - Destek / Teknosa günlük gelen cihaz listelerini (`Destek ... Data.xlsx`, `.xls`, `.csv`) tek tıkla içeri aktarma.
   - **Otomatik Çift Kayıt Engelleme:** Dosyadaki ve sistemdeki 8.699+ IMEI çapraz taranarak mükerrer kayıtlar engellenir.
   - **Model Tavan Fiyatı Otomatik Eşleştirme:** 634 modelin tavan fiyatı otomatik atanır.

3. **Canlı Formül & Hakediş Hesaplama:**
   - Apple ve Android için 11 ekspertiz sorusuna göre canlı **Eksi Puan** hesabı.
   - **Hakediş Fiyatı (AS Formülü):** `=ROUNDUP(IF(AT>90, AU*0.10, AU*(100-AT)/100))`
   - **Mutabakat Farkı (AV Formülü):** `=FİYAT - Çek Tutarı`

4. **Yazdırılabilir Mutabakat Fişi:**
   - Her işlem için A4 formatında teslim ve ekspertiz raporu.

5. **Kurumsal Excel (.xlsx) Dışa Aktarma:**
   - Filtrelenen veya tüm veritabanı kayıtlarını kurumsal formatta indirme.

---

## 🛠️ Kurulum ve Çalıştırma

### 1. Bağımlılıkları Yükleyin:
```bash
pip install -r requirements.txt
```

### 2. Portalı Başlatın:
Windows üzerinde `BASLAT_MUTABAKAT_PORTALI.bat` dosyasına çift tıklayın veya terminalden:
```bash
python run_mutabakat.py
```

### 3. Tarayıcıdan Erişin:
- **Yerel Erişim:** [http://localhost:8080](http://localhost:8080)
- **Ağdan / Online Erişim:** `http://<IP_ADRESINIZ>:8080`

---

## 👥 Kullanıcı Rolleri ve Giriş Bilgileri

| Rol | Kullanıcı Adı | Şifre | Yetkiler |
|---|---|---|---|
| **Yönetici (Admin)** | `admin` | `admin123` | Günlük Excel yükleme, silme, kullanıcı yönetimi, tam yetki |
| **Operatör** | `operator` | `operator123` | Cihaz inceleme, ekspertiz soruları puanlama, Excel rapor alma |

---

## 📁 Proje Mimarisi

- `mutabakat_portal/`: FastAPI web uygulaması, şablonlar ve formül servisleri.
- `data/teknosa_mutabakat.db`: SQLite ilişkisel veritabanı (WAL modu & IMEI indeksli).
- `run_mutabakat.py`: Uvicorn web sunucusu başlatıcısı.
- `BASLAT_MUTABAKAT_PORTALI.bat`: Tek tıkla çalıştırma betiği.
