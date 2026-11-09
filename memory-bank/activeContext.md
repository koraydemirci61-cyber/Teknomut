# Active context

**Current focus**: Cihaz Fonksiyon & Hasar Sorgu Yönetimi (`/admin/questions`), Dinamik %lik Ceza Puanı Ayarları ve Değişiklik Kapsamı (Tüm Data vs. Yeni Kayıtlar) Onay Mekanizması tamamlandı.

**In progress / Completed**:
- [x] Dinamik Hasar & Fonksiyon Soru Kriterleri Yönetimi (`/admin/questions`):
  - SQLite `inspection_questions` tablosu oluşturuldu ve 11 standart soru kriteriyle dinamik olarak entegre edildi.
  - Yöneticiler için yeni soru/kriter ekleme (madde tanımı, cihaz grubu: Tüm Cihazlar / Apple / Android, sıra no ve seçenekler).
  - Her soru maddesinin %lik ceza kesinti puanlarını (örn: Kamera -%40, Kasa -%15 vb.) düzenleyebilme.
  - Madde çıkartma / pasife alma ve aktifleştirme (toggle).
- [x] Kapsam Onayı & İptal Mekanizması:
  - Değişiklik yapılırken veya yeni madde eklenirken/çıkartılırken sistem açıkça sorar:
    1. **Sadece Bundan Sonraki Kayıtlar İçin Geçerli Olsun** (`apply_scope: future`): Değişim anı itibariyle yeni girilecek ve güncellenecek mutabakat kayıtlarına uygulanır; geçmiş kayıtlar korunur.
    2. **Tüm Veritabanına Uygula & Yeniden Hesapla** (`apply_scope: all`): Mevcut tüm veritabanı (8.700+ kayıt) yeni ceza puanlarına göre anında yeniden hesaplanır.
    3. **İptal Et**: Değişiklik kaydedilmeden vazgeçilir.
- [x] Form & Fiş Entegrasyonu:
  - Cihaz giriş ve düzenleme formunda (`/mutabakat/new` ve `/mutabakat/{id}/edit`) sorular veritabanındaki aktif kriterlerden dinamik olarak yüklenir; JavaScript canlı hesaplayıcısı seçeneklerin `data-penalty` değerlerini dinamik olarak okur.
  - Cihaz detay fişinde (`/mutabakat/{id}`) sorular dinamik döküm olarak listelenir.

**Decisions (recent)**:
- Yönetici hasar/ceza puanlarını değiştirdiğinde geçmiş datayı koruma veya tümünü yeniden hesaplama inisiyatifi yöneticiye bırakıldı.

**Open questions**:
- Yok. Sistem tam çalışır durumda.
