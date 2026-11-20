@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_seans.py --open-browser
) else (
    python run_seans.py --open-browser
)
if errorlevel 1 (
    echo.
    echo Sunucu baslatilamadi. Yukaridaki hata mesajini kontrol edin.
)
pause
