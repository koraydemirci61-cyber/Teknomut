# Progress

**What works**
- Teknosa Mutabakat ve Hakediş Yönetim Portalı:
  - 8.769 adet gerçek mutabakat kaydı SQLite'a yüklendi.
  - **2 Adımlı Günlük Veri Yükleme**:
    - **1. Buton (Kontrol Et & Doğrula)**: Dosyayı veritabanına yazmadan ayrıştırır, mükerrerleri, model fiyatlarını ve satır önizlemesini sunar.
    - **2. Buton (İçe Aktarımı Başlat)**: Kontrol edilmeden kilitlidir, kontrol onaylandıktan sonra aktifleşir.
  - **Son Aktarımı Geri Alma (Undo)**: En son yüklenen aktarım paketindeki tüm cihazları tek tıkla silerek veritabanını önceki haline döndürür.
  - **Tüm Datayı Güncelle**: Tüm veritabanındaki 8.700+ kaydın soru puanlarını, tavan fiyatlarını ve mutabakat farklarını tek tıkla günceller.
  - **Toplu Seri / IMEI Silme Sayfası (`/admin/bulk-delete`)**:
    - Metin kutusuna yapıştırılan IMEI'leri bulup önizleme ve kalıcı olarak silme.
    - Geçmiş aktarım paketlerini listeleme ve istenen paketi tamamen geri alma/silme.
  - Rol bazlı yetkilendirme (Admin / Operatör).
  - Dashboard & Raporlama Merkezi:
    - **Silinen / Boş IMEI Otomatik Temizleme (Purge)**: IMEI'si silinen ya da boşaltılan tüm satırların veritabanından kalıcı olarak silinmesi garantilendi (SQLite Triggers ve `WHERE imei IS NOT NULL AND TRIM(imei) != ''` filtreleri). Hiçbir raporda veya göstergede yer alamaz.
    - **Canlı Veritabanı Senkronizasyonu**: Önbellek engelleme başlıkları (`no-cache, no-store`) ve tek tıkla **"Raporu Yenile"** canlı güncelleme butonu.
    - **Sütun Başlıklarına Göre Çift Yönlü Sıralama**: Tablolardaki tüm başlıklara tıklayarak büyükten küçüğe (▼) veya küçükten büyüğe (▲) anlık interaktif sıralama.
    - **Finansal Kural**: Uyuşmazlık ve fark hesapları yalnızca statüsü **"Mutabakat tamamlandı"** olan kayıtlar için hesaplanıyor.
    - **Ölçüt Seçimi**: Adete Göre, Total Tutara Göre veya Fark Tutarına Göre sıralama.
    - **3 Boyutlu Raporlama Sekmeleri**: Mağaza Bazlı, Temsilci Bazlı ve Model Bazlı raporlama.
    - **Cihaz Modeli Filtresi**: 300+ cihaz modeli seçimi.
    - Haftalık, Aylık, 3 Aylık ve Özel Tarih filtreleme.
    - 5 Sekmeli Kapsamlı Yönetici Excel Raporu (`.xlsx`).
  - Mutabakat Listesi ve Arama: Mağaza, temsilci, model, tarih aralığı, statü ve fark durumuna göre filtreleme.
  - Canlı sunucu `http://localhost:8080` üzerinde kesintisiz çalışıyor.

**Not started / backlog**
- İleride istenirse departman bazlı ek alt kırılımlar veya SMS/E-posta bildirimleri eklenebilir.

**Known issues**
- Yok. Tüm testler başarıyla geçti.
