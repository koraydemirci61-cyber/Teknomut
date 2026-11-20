"""Run the standalone LAN session-planning portal."""
import argparse
import csv
import os
from pathlib import Path
import socket
import subprocess

from seans_portal.database import initialize
from seans_portal.services import PortalError, import_workbook

ROOT = Path(__file__).resolve().parent


def protect_data_directory(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            user = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True,
            )
            sid = next(csv.reader([user.stdout.strip()]))[1]
            subprocess.run(
                ["icacls", str(directory), "/inheritance:r", "/grant:r",
                 f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
                capture_output=True, check=True,
            )
        else:
            directory.chmod(0o700)
    except Exception as exc:
        # Ev veya kısıtlı ortamlarda izin hatası durumunda uygulamanın durmasını önler
        pass


def local_addresses() -> list[str]:
    return sorted({
        item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        if not item[4][0].startswith(("127.", "169.254."))
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "seans_portal")
    parser.add_argument("--import-excel", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port 1-65535 araliginda olmali.")
    directory = args.data_dir.resolve()
    protect_data_directory(directory)
    database = directory / "seans.db"
    initialize(database)

    # Eski geçici dosya temizlikleri
    (directory / "YONETICI_GIRIS.txt").unlink(missing_ok=True)
    (directory / "YONETICI_GIRIS.html").unlink(missing_ok=True)

    if args.import_excel:
        try:
            count = import_workbook(database, args.import_excel.read_bytes())
        except (PortalError, OSError) as exc:
            parser.error(str(exc))
        print(f"{count} personel aktarildi.")

    try:
        addresses = local_addresses()
    except socket.gaierror as exc:
        print(f"Ag adresi belirlenemedi: {exc}. ipconfig ile IPv4 adresini kontrol edin.")
        addresses = []

    primary_ip = addresses[0] if addresses else "127.0.0.1"
    share_link = f"http://{primary_ip}:{args.port}/"
    admin_link = f"http://127.0.0.1:{args.port}/yonetim"

    print("=" * 68)
    print("   DESTEK BİLİŞİM - İŞ SAĞLIĞI VE GÜVENLİĞİ EĞİTİMİ OTURUM PLANI")
    print("=" * 68)
    print(f" Şeflerle Paylaşılacak Tek Link : {share_link}")
    print(f" Yönetim Paneli (Excel & Ayar)  : {admin_link}")
    print("-" * 68)
    print(" Bilgi: Şefler için ayrı linke ve parolaya gerek yoktur.")
    print(" Her şef linke girip departmanını seçerek 4 oturumdan birini belirler.")
    print(" Yönetici istediği an Yönetim Paneli'nden Excel dökümü alabilir.")
    print("=" * 68)
    print(" Sunucu çalışıyor... (Kapatmak için Ctrl+C)")
    print()

    if not args.prepare_only:
        import uvicorn
        from seans_portal.app import create_app
        if args.open_browser:
            import webbrowser
            webbrowser.open(admin_link)
        uvicorn.run(create_app(database), host=args.host, port=args.port,
                    access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
