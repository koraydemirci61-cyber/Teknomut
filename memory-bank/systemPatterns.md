# System patterns

Document **architecture** and **recurring patterns** so Copilot stays aligned.

- **High-level layout**:
  - `personel_portal/`
    - `app.py`: FastAPI web uygulaması & rotalar
    - `database.py`: SQLite veritabanı bağlantı ve şema yönetimi
    - `models.py`: Veritabanı modelleri ve pydantic şemaları
    - `services/auth.py`: PBKDF2 hashleme ve oturum yönetimi
    - `services/calculator.py`: Formül hesaplama motoru (Excel formüllerinin birebir izdüşümü)
    - `services/importer.py`: `personel_degerlendirme_kopya.xlsx` dosyasından ilk aktarım
    - `services/exporter.py`: Güncel değerlendirmeleri Excel dosyasına geri aktarım
    - `templates/`: Jinja2 HTML şablonları (login, dashboard, personel listesi, puanlama formu, raporlama)
    - `static/`: Stil ve JavaScript betikleri

- **Data flow**:
  1. Kullanıcı tarayıcıdan giriş yapar -> Oturum tokeni oluşturulur.
  2. Personel listesi SQLite üzerinden sorgulanır.
  3. Değerlendirme ekranında puanlar girilirken `calculator.py` mantığı ile istemcide ve sunucuda hesaplanır.
  4. Kaydedilen veriler SQLite `evaluations` tablosuna yazılır.
  5. Raporlama ve Excel çıktısı güncel veritabanından dinamik üretilir.

- **Patterns to follow**:
  - SQLite parametreli sorgular (SQL injection önleme).
  - Güvenli parola saklama (PBKDF2-HMAC-SHA256).
  - Türkçe karakter ve UTF-8 tam desteği.
  - Modüler ve temiz kod ayrımı.
