@echo off
chcp 65001 > nul
title Teknosa Buyback Mutabakat Portali
cd /d "%~dp0"

echo ======================================================================
echo           TEKNOSA BUYBACK VE MUTABAKAT YONETIM PORTALI
echo ======================================================================
echo Program ve Veritabani bu bilgisayarda calisiyor.
echo.
echo Bu Bilgisayardan Tarayici ile : http://localhost:8080
echo Agdaki Diger Kullanicilar     : http://192.168.20.221:8080
echo ----------------------------------------------------------------------
echo Hazir Kullanici Hesaplari:
echo   1) Yonetici (Admin)        : admin    / admin123  (Tam Yetkili - DB & Kullanici Yonetimi)
echo   2) Operator                : operator / operator123 (Sadece Mutabakat Listesi & Kayit Duzenleme)
echo   3) Gozetmen                : gozetmen / gozetmen123 (Dashboard & Rapor Inceleme - Salt Okunur)
echo ======================================================================
echo Sunucu baslatiliyor... (Kapatmak icin bu pencereyi kapatin)
echo.

python run_mutabakat.py
pause
