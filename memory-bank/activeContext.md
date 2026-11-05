# Active context

**Current focus**: Program ve veritabanı bu çalışma alanında kalıcı hale getirildi. Günlük Excel/CSV veri yükleme altyapısı, otomatik mükerrer kontrolü ve tek tıkla başlatıcı bat dosyası hazırlandı.

**In progress**:
- [x] Program dosyalarının (`mutabakat_portal/`) ve SQLite veritabanının (`data/teknosa_mutabakat.db`) yerel çalışma alanında yapılandırılması
- [x] Admin ve Operatör rollerinin ayrıştırılması (Admin: Günlük Excel yükleme & silme; Operatör: Puanlama & inceleme)
- [x] Günlük yükleme modülünün hem `.xlsx`, `.xls` hem de `.csv` destekleyecek şekilde güçlendirilmesi
- [x] Otomatik çift kayıt engelleme filtresinin doğrulanması (aynı IMEI tekrar yüklendiğinde kesinlikle çift satır açılmaz)
- [x] `BASLAT_MUTABAKAT_PORTALI.bat` başlatıcısının oluşturulması
- [x] Canlı sunucunun 8080 portunda arka planda çalışır durumda tutulması

**Decisions (recent)**:
- Program, veritabanı ve tüm güncellemeler doğrudan `C:\Users\koray.demirci\Desktop\python.py` dizininde tutuluyor.
- Masaüstünden veya klasörden `BASLAT_MUTABAKAT_PORTALI.bat` çalıştırılarak portal kolayca açılabilir.

**Open questions**:
- Yok. Sistem tam çalışır durumda.
