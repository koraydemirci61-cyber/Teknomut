from playwright.sync_api import sync_playwright

print("Robot çalışmaya başlıyor...")

def test_robotu():
    with sync_playwright() as p:
        # Tarayıcıyı aç (headless=False ekrandan görebilmemiz içindir)
        tarayici = p.chromium.launch(headless=False) 
        sayfa = tarayici.new_page()
        
        # Siteye git
        sayfa.goto("https://destekwega.com/Community/Login.aspx?LRP=/")
        print("Login sayfası başarıyla açıldı!")
        
        # Sayfanın yüklenmesini bekle
        sayfa.wait_for_timeout(2000)
        
        # Kullanıcı adı alanını doldur
        sayfa.fill("#UserName", "koray")
        print("Kullanıcı adı girildi.")
        
        # Şifre alanını doldur
        sayfa.fill("input[name='Password']", "3A5MF62W")
        print("Şifre girildi.")
        
        # Login butonuna tıkla
        sayfa.click("input[name='Enter']")
        print("Giriş yapılıyor...")
        
        # Giriş sonrası sayfanın yüklenmesini bekle
        sayfa.wait_for_timeout(5000)
        print("Giriş başarıyla tamamlandı!")
        
        # Alt Q (Seri Numarası İşlemleri Raporu) sayfasına git
        sayfa.goto("https://destekwega.com/Reports/SerialNumberTransactions.aspx")
        print("Alt Q sayfası açılıyor...")
        
        # Alt Q sayfasının yüklenmesini bekle
        sayfa.wait_for_timeout(5000)
        print("Alt Q sayfası başarıyla açıldı!")
        
        # Tarayıcıyı kapat
        tarayici.close()
        print("Görev tamamlandı.")

test_robotu()
