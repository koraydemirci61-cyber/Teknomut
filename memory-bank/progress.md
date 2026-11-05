# Progress

**What works**
- Google E-Tablo kopyası analiz edildi:
  - 2 sayfa: `Sayfa1` (Değerlendirme) ve `Faktörler` (Kriter Rehberi).
  - Formüller: Toplam puan ortalaması, çalışma yılı kıdem hesabı, performans kategorisi mantığı, ücret artış oranı.
- SQLite veritabanı kuruldu (`data/personel_portal.db`) ve 22 personelin verisi aktarıldı.
- Kullanıcı yetkilendirme sistemi (PBKDF2-HMAC-SHA256) hazırlandı:
  - `admin` / `admin123` (Yönetici)
  - `yonetici` / `yonetici123` (Değerlendirici)
- Web arayüzü tamamlandı:
  - Dashboard: KPI sayaçları, Performans Dağılımı ve 10 Faktör Başarı grafikleri (Chart.js).
  - Personel Listesi: Canlı isim/unvan/kriter arama ve filtreleme.
  - Puanlama Ekranı: 10 faktör için dinamik slider + sayı kutusu, anlık canlı toplam puan ve renkli rozet hesaplaması.
  - Personel Ekleme / Düzenleme formu: Canlı kıdem ve maaş artış oranı hesaplama.
  - Kurumsal Performans Karnesi (Yazdırılabilir / PDF uyumlu A4 şablonu ve imza blokları).
  - Excel (.xlsx) dışa aktarım motoru (openpyxl ile kurumsal formatta çift sayfalı çıktı).
  - Kullanıcı yönetimi paneli (yöneticiler için yeni kullanıcı oluşturma).
- Başlatıcı betik (`run_portal.py`) eklendi.

**Not started / backlog**
- İleride istenirse departman bazlı ek alt kırılımlar veya SMS/E-posta bildirimleri eklenebilir.

**Known issues**
- Yok. Tüm testler başarıyla geçti.
