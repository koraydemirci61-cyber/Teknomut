# Active context

**Current focus**: IMEI'si silinen / boşaltılan tüm satırların veritabanından kalıcı olarak temizlenmesi kuralı uygulandı. Veritabanı tetikleyicileri (triggers), başlangıç ve sorgu filtreleri ile IMEI'si olmayan hiçbir kaydın raporlarda yer almaması sağlandı.

**In progress / Completed**:
- [x] Veritabanı Tetikleyicileri (Triggers):
  - `trg_purge_empty_imei_insert` ve `trg_purge_empty_imei_update` tetikleyicileri eklendi.
  - IMEI'si boş (`''`), `NULL` veya 8 karakterden kısa olan satırlar INSERT veya UPDATE anında veritabanı motoru tarafından anında kalıcı olarak silinir.
- [x] Web Arayüzünde IMEI Silme Kuralı:
  - Cihaz düzenleme formunda (`/mutabakat/{id}/edit`) IMEI alanı silinirse veya boş bırakılırsa, cihaza ait tüm veriler (müşteri, çek tutarı, hakediş vb.) veritabanından kalıcı olarak silinir.
- [x] Rapor & Sorgu Filtreleri:
  - Dashboard analitik sorguları, sayaçlar, grafikler, mutabakat listesi ve Excel dışa aktarımında `WHERE imei IS NOT NULL AND TRIM(imei) != '' AND LENGTH(TRIM(imei)) >= 8` şartı zorunlu kılındı.
- [x] İçe Aktarma Koruması:
  - Günlük dosyalarda IMEI'si silinmiş/boş satırlar otomatik olarak atlanır, sisteme alınmaz.

**Decisions (recent)**:
- IMEI'si silinen bir cihazın hiçbir finansal veya müşteri verisi veritabanında tutulmaz, tüm satır kalıcı olarak silinir.

**Open questions**:
- Yok. Sistem tam çalışır durumda.
