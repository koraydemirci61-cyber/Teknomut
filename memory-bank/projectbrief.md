# Project brief

Teknosa Buyback Cihaz Geri Alım ve Mutabakat Yönetim Portalı (Web & SQLite Veritabanı).
Google Drive üzerindeki "TEKNOSA MUTABAKAT" E-Tablosunun tam kopyası (`teknosa_mutabakat_kopya.xlsx`) indirilip 4 sayfası, formülleri ve bağlantıları çözümlenerek; kullanıcı girişi olan, SQLite veritabanına 8.699+ kaydı aktarılmış, canlı hasar/ekspertiz soru puanı hesaplayan ve Excel/Fiş raporları üreten online web portalı.

- **Goal**:
  1. Google Drive E-Tablosu (`TEKNOSA MUTABAKAT`) kopyasının tüm sayfalarını (`MUTABAKAT`, `YENİ SORU SETLERİ`, `ESKİ SORU SETLERİ`, `VERİ-DATA`), formüllerini ve bağlantılarını analiz etmek.
  2. Tablodaki 8.699 adet mutabakat kaydını ve 634 model tavan fiyatını ilişkisel SQLite veritabanına (`data/teknosa_mutabakat.db`) aktarmak.
  3. Kullanıcı girişi (admin/operator) ile güvenli online web arayüzü sunmak.
  4. Yeni cihaz girişinde ve düzenlemede ekspertiz sorularına göre canlı Eksi Puan, Hakediş Fiyatı (`ROUNDUP(IF(AT>90, AU*0.10, AU*(100-AT)/100))`), Fark (`FİYAT - Çek Tutarı`) ve Çift IMEI kontrolü çalıştırmak.
  5. Dashboard KPI sayaçları, Chart.js grafikleri, filtreli liste ve kurumsal Excel (.xlsx) dışa aktarımı sağlamak.

- **Success criteria**:
  - Tüm kayıtların veritabanında saklanması ve hızlı aranabilmesi.
  - Canlı formül hesaplamalarının Excel ile birebir tutarlı olması.
  - Web sunucusunun çalıştırılıp yerel ve ağ üzerinden erişilebilir olması.
