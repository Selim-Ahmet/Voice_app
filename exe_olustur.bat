@echo off
chcp 65001 > nul
echo =====================================================
echo   VoiceLink - EXE Olusturucu
echo =====================================================
echo.
echo Bu islem birkaç dakika surebilir...
echo.

where py >nul 2>&1
if not errorlevel 1 (
    set PY=py
) else (
    set PY=python
)

:: Eski build temizle
if exist dist\VoiceLink.exe (
    echo Eski exe siliniyor...
    del /q dist\VoiceLink.exe
)
if exist build rmdir /s /q build
if exist VoiceLink.spec del /q VoiceLink.spec

:: EXE olustur
echo PyInstaller calistiriliyor...
%PY% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name VoiceLink ^
    --hidden-import pyaudio ^
    voice_chat.py

if errorlevel 1 (
    echo.
    echo [HATA] EXE olusturulamadi!
    echo kurulum.bat'i calistirip tekrar deneyin.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo   BASARILI! EXE hazir:
echo   dist\VoiceLink.exe
echo.
echo   Bu dosyayi arkadaslarına at, hepsi calistirir.
echo   Python kurulu olmasi gerekmez.
echo =====================================================

:: dist klasorunu ac
explorer dist

pause
