# Teknosa Buyback Mutabakat ve Hakediş Yönetim Portalı

Teknosa mağazalarından geri alınan (Buyback) ikinci el cihazların ekspertiz kontrollerini, hasar ve fonksiyon test puanlarını, liste tavan değerlerini ve çek tutarı mutabakatlarını yöneten online web portalı.

---

## 🚀 GitHub Depodan Kurulum ve Çalıştırma

### 1. Depoyu Klonlayın:
```bash
git clone https://github.com/koraydemirci61-cyber/Teknomut.git
cd Teknomut
```

### 2. Gerekli Kütüphaneleri Yükleyin:
```bash
pip install -r requirements.txt
```

### 3. Portalı Başlatın:
Windows üzerinde **`BASLAT_MUTABAKAT_PORTALI.bat`** dosyasına çift tıklayarak veya terminalden:
```bash
python run_mutabakat.py
```

### 4. Tarayıcıdan Giriş Yapın:
- **Yerel Erişim:** [http://localhost:8080](http://localhost:8080)
- **Ağdan / Online Erişim:** `http://<IP_ADRESINIZ>:8080`

### 👥 Hazır Kullanıcı Hesapları:
| Rol | Kullanıcı Adı | Şifre | Yetkiler |
|---|---|---|---|
| **Yönetici (Admin)** | `admin` | `admin123` | Günlük Excel yükleme, kontrol & aktarım, son aktarımı geri alma, toplu seri silme, tam yetki |
| **Operatör** | `operator` | `operator123` | Cihaz arama/listeleme, ekspertiz soruları düzenleme, fiş görüntüleme, Excel rapor alma |

---

## 🌟 Sistem Yetenekleri ve Modülleri

### 1. 📊 Dashboard & Gelişmiş Raporlama Merkezi (`/dashboard`)
* **Dönemsel Analiz:** Haftalık (Son 7 Gün), Aylık (Son 30 Gün), 3 Aylık (Son 90 Gün), Tüm Zamanlar ve Özel Tarih Aralığı.
* **3 Boyutlu Raporlama Sekmeleri:**
  * **🏪 Mağaza Bazlı Rapor:** 145 Teknosa mağazasının işlem adedi, verilen çek toplamı, hakediş ve mutabakat farkları.
  * **👤 Temsilci Bazlı Rapor:** 1.235 mağaza temsilcisinin kabul ettiği cihaz adetleri, ciro ve uyuşmazlıkları.
  * **📱 Model Bazlı Rapor:** Cihaz modellerinin (Apple, Samsung, Xiaomi vb.) adet, tutar ve mutabakat farkları.
* **Sıralama Seçenekleri:** Adete Göre (İşlem Sayısı), Total Tutara Göre (Verilen Çek ₺) veya Net Farka Göre (₺).
* **Başlıklara Göre İnteraktif Çift Yönlü Sıralama:** Tablolardaki tüm sütun başlıklarına tıklayarak büyükten küçüğe (▼) veya küçükten büyüğe (▲) anlık sıralama.
* **Finansal Doğruluk Kuralı:** Uyuşmazlık ve fark hesapları yalnızca **"Mutabakat tamamlandı"** statüsündeki kayıtlar için hesaplanır; sonuçlanmamış bekleyen kayıtlar finansal fark bakiyesini bozmaz.
* **Canlı Veritabanı Senkronizasyonu:** Sayfa açıldığında veya `[Raporu Yenile]` tıklandığında önbelleksiz olarak SQLite'tan canlı veriler çekilir.
* **5 Sekmeli Yönetici Excel Raporu:** Yönetici Özeti, Mutabakat Detayı, Mağaza Performansı, Temsilci Performansı ve Model Performansı.

### 2. 🛡️ 2 Adımlı Günlük Veri Yükleme (`/import/daily`)
* **1. Buton (Dosyayı Kontrol Et & Doğrula):** Dosyayı veritabanına yazmadan ayrıştırır, mükerrerleri, model fiyatlarını ve satır önizlemesini sunar.
* **2. Buton (İçe Aktarımı Başlat):** Kontrol edilmeden kilitlidir, kontrol raporu onaylandıktan sonra aktifleşir.
* **Otomatik Çift Kayıt Engelleme:** Dosya içi ve sistemdeki kayıtlar çapraz taranarak mükerrer IMEI'ler engellenir veya isteğe bağlı güncellenir.
* **Son Aktarımı Geri Alma (Undo):** En son yüklenen aktarım paketindeki tüm cihazları tek tıkla silerek veritabanını önceki haline döndürür.
* **Tüm Datayı Güncelle:** Tüm 8.700+ kaydın soru puanlarını, tavan fiyatlarını ve mutabakat farklarını tek tıkla yeniden hesaplar.

### 3. 🗑️ Toplu Seri / IMEI Silme Merkezi (`/admin/bulk-delete`)
* **IMEI / Seri Listesi ile Silme:** Metin alanına yapıştırılan IMEI'leri bulup önizler ve tek onay ile veritabanından kalıcı olarak siler.
* **Aktarım Paketi (Batch) Bazında Silme:** Geçmiş aktarım paketlerini listeler ve istenen paketi tamamen geri alır.
* **Kalıcı Temizleme Kuralı:** IMEI'si silinen veya boşaltılan hiçbir cihazın müşteri/finansal verisi sistemde tutulmaz, veritabanı tetikleyicileri (Triggers) ile satır tamamen temizlenir ve raporlarda asla yer almaz.

### 4. 📱 Canlı Formül & Hakediş Ekspertiz Motoru
* 11 ekspertiz sorusuna göre canlı **Eksi Puan** hesabı.
* **Hakediş Değeri (AS Formülü):** `=ROUNDUP(IF(AT>90, AU*0.10, AU*(100-AT)/100))`
* **Mutabakat Farkı (AV Formülü):** `=Hakediş - Çek Tutarı`
* A4 formatında yazdırılabilir / PDF çıktı uyumlu **Mutabakat ve Ekspertiz Fişi**.

---

## 📁 Proje Dosya Yapısı

```
Teknomut/
├── mutabakat_portal/
│   ├── app.py                     # FastAPI ana web uygulaması ve rotalar
│   ├── database.py                # SQLite veritabanı bağlantısı, şema ve tetikleyiciler
│   ├── services/
│   │   ├── auth.py                # Kullanıcı oturum ve şifreleme (PBKDF2)
│   │   ├── calculator.py          # Eksi puan ve hakediş değerleme formülleri
│   │   ├── daily_importer.py      # 2 adımlı Excel/CSV yükleme, ön kontrol, geri alma ve toplu silme
│   │   └── exporter.py            # 5 sekmeli kurumsal Excel (.xlsx) dışa aktarma motoru
│   └── templates/
│       ├── base.html              # Kurumsal Tailwind + FontAwesome iskelet şablonu
│       ├── dashboard.html         # Çok boyutlu filtreli ve sıralanabilir analitik merkezi
│       ├── daily_upload.html      # 2 adımlı yükleme ve geri alma yönetim ekranı
│       ├── bulk_delete.html       # Toplu IMEI ve paket silme ekranı
│       ├── mutabakat_list.html    # Filtreli ve sayfalanmış kayıtlar tablosu
│       ├── mutabakat_form.html    # Ekspertiz soru ve değerleme formu
│       ├── mutabakat_detail.html  # Yazdırılabilir A4 mutabakat fişi
│       └── login.html             # Güvenli oturum açma sayfası
├── data/
│   └── teknosa_mutabakat.db       # SQLite ilişkisel veritabanı
├── BASLAT_MUTABAKAT_PORTALI.bat   # Windows tek tıkla başlatıcı
├── run_mutabakat.py               # Uvicorn sunucu başlatıcı
├── requirements.txt               # Python bağımlılıkları
└── README.md                      # Proje ve kurulum dokümantasyonu
```
