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
  - **Kullanıcı & Şifre Yönetimi Paneli (`/admin/users`)**:
    - Aynı anda 15+ kullanıcının eşzamanlı erişimini destekleyen SQLite WAL ve bağlantı havuzu optimizasyonu.
    - Yöneticiler için yeni kullanıcı oluşturma (kullanıcı adı, şifre, rol, e-posta).
    - Her kullanıcı için anında şifre sıfırlama / güncelleme.
    - Kullanıcı hesabı pasife alma / aktifleştirme ve güvenli silme.
    - Üst menüde Admin'e özel "Kullanıcılar" sekmesi.
  - **Hasar & Fonksiyon Soru Kriterleri ve Ceza Puanı Yönetimi (`/admin/questions`)**:
    - Yöneticiler için yeni kontrol maddesi ekleme, maddeleri düzenleme, çıkartma (pasife alma) ve aktifleştirme.
    - Her sorunun cevap seçeneklerine göre %lik ceza kesinti puanlarını (örn: -%10, -%15, -%40) anında güncelleyebilme.
    - **Kapsam Seçimi**: Değişiklik yapılırken "Sadece bundan sonraki yeni/düzeltilecek kayıtlar için mi" yoksa "Tüm veritabanındaki 8.700+ cihaz için mi" geçerli olacağını soran onay mekanizması ve iptal seçeneği.
    - Cihaz giriş/düzenleme formunda ve fiş dökümünde dinamik soru ve canlı JavaScript puan hesaplama entegrasyonu.
  - **3 Seviyeli Rol & Yetkilendirme Sistemi (Admin, Operatör, Gözetmen)**:
    - **Yönetici (Admin)**: Veritabanında tam yetkili düzeltme/güncelleme, dosya yükleme, toplu silme, kullanıcı/şifre yönetimi ve Excel dışa aktarımı.
    - **Operatör**: Girişte doğrudan Mutabakat Listesi ekranı açılır (`/mutabakat`); yalnızca kayıtları inceleme, filtreleme ve cihaz/soru düzenleme yetkisine sahiptir.
    - **Gözetmen**: Veri giriş/çıkışı yapamaz (Excel indirme, düzenleme, silme ve veri ekleme engellidir); girişte doğrudan Dashboard'u açarak tüm rapor varyasyonlarını (Mağaza/Temsilci/Model sekmeleri, Adet/Tutar/Fark sıralamaları) inceler.
  - Rol bazlı yetkilendirme (Admin / Operatör / Gözetmen).
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
