# Personel Seans Planlama Portalı

Mevcut mutabakat/değerlendirme uygulamalarından bağımsız, yerel ağda çalışan
FastAPI + SQLite personel oturum planlama panelidir.

## 🚀 Hızlı Başlangıç

1. Depo kökündeki **`BASLAT_SEANS_PORTALI.bat`** dosyasına çift tıklayın.
   (Alternatif terminal komutu: `.\.venv\Scripts\python.exe run_seans.py`)
2. Sunucu başladığında ekranda iki adet link göreceksiniz:
   - **Şeflerle Paylaşılacak Tek Link:** `http://<BİLGİSAYAR_IP_ADRESİNİZ>:8090/`
   - **Yönetim ve Excel Raporu:** `http://127.0.0.1:8090/yonetim` (veya `http://<IP>:8090/yonetim`)
3. **Parola ve Ayrı Link Yoktur:**
   - Her departman için ayrı linke gerek yoktur; tüm şefler aynı linke girer.
   - Hiçbir kullanıcı parola veya TC/Sicil numarası girmez.

## 👥 Departman Şefinin Kullanımı (Çok Kolay & Hızlı)

1. Şef, kendisine iletilen linke tıklar (`http://<IP>:8090/`).
2. Sayfadaki **"Departmanınızı Seçin"** açılır kutusundan kendi birimini seçer (Örn: *14.Lojistik & Depo*).
3. Seçtiği anda departmanına ait personeller hazır liste olarak ekrana gelir:
   - Personel Adı Soyadı
   - İşyeri
   - Katılacağı Seans / Oturum seçenekleri
4. Şef, her personelin karşısındaki seansı doğrudan tıklar.
5. Eğer bir personel eğitime **katılamayacaksa**, **Katılamayacak** seçeneğini işaretler ve açılan kutucuğa nedenini yazar (Zorunlu kısa açıklama).
6. Sayfanın altındaki yeşil **"Değişiklikleri Kaydet"** butonuna basar.
7. Ekranda *"Seçimleriniz başarıyla kaydedildi!"* mesajını görünce sayfayı kapatabilir.

## 📊 Yöneticinin Kullanımı ve Excel Dökümü Alma

1. Yönetici, tarayıcıda `http://127.0.0.1:8090/yonetim` adresini açar (veya sayfa üstündeki **"📊 Yönetim & Excel Raporu"** bağlantısına tıklar).
2. **Seans Tanımlama:**
   - Personellerin katılabileceği seansları (Oturum adı, tarih ve saat) ekleyebilir veya silebilir.
3. **Excel Dökümü:**
   - Yeşil **"Excel Raporunu İndir (.xlsx)"** butonuna tek tıkla basar.
   - İndirilen Excel'de (`seans_katilim_listesi.xlsx`):
     - **KATILIM LİSTESİ Sayfası:** Tüm personelin T.C. Kimlik No, Sicil No (varsa), Adı Soyadı, İşyeri, Departmanı, Seçilen Seansı, Seans Tarih/Saati, Katılım Durumu (Katılacak / Katılamayacak / Seçilmedi), Katılamama Açıklaması ve Son Güncelleme Zamanı yer alır.
     - **SEANS ÖZETİ Sayfası:** Hangi seansa kaç personelin katılacağı, kaç kişinin katılamayacağı, kaç kişinin henüz seçim beklediği özet tablosu olarak sunulur.
4. **Gizlilik Güvencesi:**
   - Şefler giriş yaparken kesinlikle TC Kimlik No veya Sicil No görmez ve girmez.
   - Yönetici Excel dökümü aldığında tüm resmi kimlik ve sicil bilgileri raporda eksiksiz görünür.

## 🌐 Ağ Bilgileri

- Port: **8090** (Mevcut 8000 ve 8080 portallarından bağımsızdır).
- Sunucu bilgisayar açık ve personellerle aynı yerel ağda (intranet/Wi-Fi/VPN) olmalıdır.
- Başlatıcı ekranında görünen yerel IP adresi (Örn: `192.168.20.221:8090`) şeflerle paylaşılır.

## 🧪 Testler

```powershell
.\.venv\Scripts\python.exe -m unittest test_seans_portal -v
```
