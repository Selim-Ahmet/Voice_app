@echo off
chcp 65001 > nul
where py >nul 2>&1
if not errorlevel 1 (
    py voice_chat.py
) else (
    python voice_chat.py
)
if errorlevel 1 (
    echo.
    echo [HATA] Program baslatılamadi. kurulum.bat dosyasini once calistirin.
    pause
)
