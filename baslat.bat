@echo off
rem AutoSell - Windows baslatici. Cift tiklayin: ilk seferde her seyi kurar, sonra paneli acar.
setlocal
cd /d "%~dp0"
title AutoSell

rem ---- Python 3.10 veya ustunu bul
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :python_yok
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :python_yok

rem ---- Sanal ortam (ilk calistirmada)
if not exist ".venv\Scripts\python.exe" (
  echo [AutoSell] Ilk kurulum yapiliyor. Birkac dakika surebilir, pencereyi kapatmayin...
  %PY% -m venv .venv
  if errorlevel 1 goto :hata
)

rem ---- Paketler: ilk seferde ve pyproject.toml degistiginde (git pull sonrasi) kurulur
fc /b pyproject.toml ".venv\kurulum-pyproject.toml" >nul 2>nul
if errorlevel 1 (
  echo [AutoSell] Gerekli paketler kuruluyor...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto :hata
  echo [AutoSell] Otomasyon tarayicisi indiriliyor...
  ".venv\Scripts\python.exe" -m playwright install chromium
  if errorlevel 1 goto :hata
  copy /y pyproject.toml ".venv\kurulum-pyproject.toml" >nul
)

if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

echo.
echo [AutoSell] Panel aciliyor: http://127.0.0.1:8000
echo [AutoSell] Kapatmak icin bu pencereyi kapatin.
echo.
".venv\Scripts\python.exe" -m autosell panel --ac
echo.
pause
exit /b 0

:python_yok
echo.
echo [AutoSell] Python 3.10 veya ustu bulunamadi.
echo   1) https://www.python.org/downloads/ adresinden Python'u indirin.
echo   2) Kurulumun ilk ekraninda "Add python.exe to PATH" kutusunu isaretleyin.
echo   3) Kurulum bitince bu dosyaya tekrar cift tiklayin.
echo.
pause
exit /b 1

:hata
echo.
echo [AutoSell] Kurulumda bir hata oldu. Yukaridaki hata mesajini kopyalayip gonderin.
echo.
pause
exit /b 1
