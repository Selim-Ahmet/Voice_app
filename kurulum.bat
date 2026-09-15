@echo off
chcp 65001 > nul
echo =====================================================
echo   VoiceLink - Kurulum
echo =====================================================
echo.

:: Windows py launcher'i dene, yoksa duz python
where py >nul 2>&1
if not errorlevel 1 (
    set PY=py
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set PY=python
    ) else (
        echo [HATA] Python bulunamadi!
        echo Python'u https://www.python.org/downloads/ adresinden indirin.
        echo Kurulum sirasinda "Add Python to PATH" secenegini isaretleyin.
        pause
        exit /b 1
    )
)

echo Kullanilan Python:
%PY% --version
echo.

echo [1/3] pip guncelleniyor...
%PY% -m pip install --upgrade pip --quiet

echo [2/3] Kutuphaneler kuruluyor (pyaudio + keyboard)...
%PY% -m pip install pyaudio
if errorlevel 1 (
    echo PyAudio direkt kurulamadi, alternatif deneniyor...
    %PY% -m pip install pipwin --quiet
    %PY% -m pipwin install pyaudio
)
%PY% -m pip install keyboard

echo [3/3] PyInstaller kuruluyor (exe olusturmak icin)...
%PY% -m pip install pyinstaller --quiet

echo.
echo =====================================================
echo   Kurulum tamamlandi!
echo   - Programi test etmek: calistir.bat
echo   - Tek .exe olusturmak: exe_olustur.bat
echo =====================================================
pause
