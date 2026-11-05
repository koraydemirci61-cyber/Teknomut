# Product context

Explain **why** this product exists and the experience you want users to have.

- **Problem**: Manuel Excel veya Google E-Tablo üzerinden personel değerlendirmesi yaparken yetkisiz erişim riski, formüllerin bozulma tehlikesi, aynı anda veri girişinde çakışmalar ve raporlama güçlüğü yaşanması.
- **Primary users**: Şube Müdürleri, Şefler, İK Yöneticileri ve Personel Değerlendiricileri.
- **UX principles**:
  - Kolay ve anlaşılır Türkçe arayüz (TailwindCSS destekli temiz tasarım).
  - Canlı formül hesaplama: Puanlar girilir girilmez toplam puan ve "Mükemmel / Yeterli / İyileştirme Gerekiyor / Yetersiz" seviyesi anında güncellenmeli.
  - Kriter rehberi: 10 faktörün detaylı açıklamaları puanlama esnasında rehber olarak görüntülenebilmeli.
  - Hızlı filtreleme ve arama.
- **Constraints**:
  - Windows ortamında yerel ve intranet üzerinden erişilebilir olmalı.
  - Veri kaybını önleyen güvenli SQLite yapısı.
