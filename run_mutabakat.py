"""
Teknosa Mutabakat ve Hakediş Portalı Başlatıcı
Çalıştırmak için: python run_mutabakat.py
"""
import uvicorn
import socket

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 8080
    
    print("=" * 70)
    print("      TEKNOSA BUYBACK VE MUTABAKAT YÖNETİM PORTALI")
    print("=" * 70)
    print(f" Bu Bilgisayardan Erişim      : http://localhost:{port}")
    print(f" Ağdan / Online Erişim        : http://{local_ip}:{port}")
    print("-" * 70)
    print(" Hazır Giriş Hesapları:")
    print("   1) Yönetici (Admin)        : admin    / admin123  (Tam Yetkili - Veritabanı & Kullanıcı Yönetimi)")
    print("   2) Operatör                : operator / operator123 (Sadece Mutabakat Listesi & Kayıt Düzenleme)")
    print("   3) Gözetmen                : gozetmen / gozetmen123 (Dashboard & Rapor Varyasyonları - Salt Okunur)")
    print("=" * 70)
    print(" Sunucu başlatılıyor... (Durdurmak için Ctrl+C)")
    print()

    uvicorn.run("mutabakat_portal.app:app", host="0.0.0.0", port=port, reload=False)
