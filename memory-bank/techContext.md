# Tech context

**Stack**

- Language / runtime: Python 3.13 (Windows x64)
- Web Framework: FastAPI
- Server: Uvicorn
- Template Engine: Jinja2
- Database: SQLite 3 (yerel `data/personel_portal.db`)
- Excel Engine: openpyxl, pandas
- Frontend: HTML5, TailwindCSS (CDN), Chart.js (CDN), FontAwesome (CDN)

**Environment**

- OS: Windows 11
- Çalışma Dizini: `C:\Users\koray.demirci\Desktop\python.py`
- Ana Kopya Excel: `personel_degerlendirme_kopya.xlsx`

**Build & Run**

- Başlatma: `python -m uvicorn personel_portal.app:app --host 127.0.0.1 --port 8000 --reload`
- Port: `http://127.0.0.1:8000` (veya yerel ağ IP'si ile online intranet erişimi)

**Constraints**

- Harici bulut bağımlılığı olmadan yerel intranet veya sunucuda çalışabilirlik.
- Türkçe karakter desteği (UTF-8).
