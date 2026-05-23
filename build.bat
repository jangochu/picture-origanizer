@echo off
REM ============================================================
REM   Photo Organizer - Windows build script
REM   Double-click on Windows 10+. Output: dist\PhotoOrganizer.exe
REM   Requires: Python 3.10+ (either on PATH, or the "py" launcher)
REM ============================================================
chcp 65001 > nul 2>nul
setlocal enableextensions

cd /d "%~dp0"

echo.
echo === [1/5] Detecting Python ===
set PY=
where python >nul 2>nul && set PY=python
if not defined PY (where py >nul 2>nul && set PY=py)
if not defined PY (
  echo.
  echo ERROR: Neither 'python' nor 'py' was found.
  echo.
  echo Fix options:
  echo  A. Re-run the Python installer, click "Modify", and check:
  echo       [x] Add Python to environment variables
  echo       [x] Install Python launcher for all users
  echo     Then open a NEW CMD window and run build.bat again.
  echo.
  echo  B. Download Python 3.10+ from:
  echo       https://www.python.org/downloads/windows/
  echo     During install, check "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)
echo Found Python launcher: %PY%
%PY% --version

echo.
echo === [2/5] Creating virtualenv .venv ===
if not exist ".venv\Scripts\activate.bat" (
  if exist .venv (
    echo Removing broken .venv ...
    rmdir /s /q .venv
  )
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo Failed to activate venv. Try deleting the .venv folder and re-run.
  pause
  exit /b 1
)

echo.
echo === [3/5] Installing Python dependencies ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo.
  echo Failed to install dependencies.
  echo If pip is slow in mainland China, try a mirror:
  echo   pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt pyinstaller
  echo Then run build.bat again.
  pause
  exit /b 1
)

echo.
echo === [4/5] Preparing exiftool.exe ===
REM exiftool.org keeps only the LATEST version on the server, so we
REM scrape the homepage for the current version number first, and
REM fall back to a known-good version if scraping fails.
set EXIFTOOL_FALLBACK_VER=13.58
set EXIFTOOL_VER=
for /f "delims=" %%v in ('powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try { $h=(Invoke-WebRequest -Uri 'https://exiftool.org/' -UseBasicParsing).Content; if ($h -match 'exiftool-([0-9]+\.[0-9]+)_64\.zip') { $matches[1] } } catch {}"') do set EXIFTOOL_VER=%%v
if not defined EXIFTOOL_VER set EXIFTOOL_VER=%EXIFTOOL_FALLBACK_VER%
set EXIFTOOL_ZIP=exiftool-%EXIFTOOL_VER%_64.zip
set EXIFTOOL_URL=https://exiftool.org/%EXIFTOOL_ZIP%
echo Using exiftool version: %EXIFTOOL_VER%

if not exist "exiftool_bundle\exiftool.exe" (
  echo Downloading exiftool from %EXIFTOOL_URL% ...
  if exist "%EXIFTOOL_ZIP%" del "%EXIFTOOL_ZIP%"
  powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%EXIFTOOL_URL%' -OutFile '%EXIFTOOL_ZIP%' -UseBasicParsing } catch { Write-Host $_; exit 1 }"
  if errorlevel 1 (
    echo.
    echo Failed to download exiftool.
    echo Please download manually from https://exiftool.org/ ,
    echo extract the zip, and place these into the exiftool_bundle\ folder:
    echo   - exiftool.exe   ^(rename from "exiftool^(-k^).exe"^)
    echo   - exiftool_files\   ^(the whole directory^)
    echo Then run build.bat again.
    pause
    exit /b 1
  )
  if exist exiftool_bundle rmdir /s /q exiftool_bundle
  powershell -NoProfile -Command "Expand-Archive -Force '%EXIFTOOL_ZIP%' -DestinationPath exiftool_bundle"
  if errorlevel 1 (
    echo Failed to extract zip.
    pause
    exit /b 1
  )
  del "%EXIFTOOL_ZIP%"
  REM exiftool's Windows zip uses the name "exiftool(-k).exe" - rename it
  for %%f in ("exiftool_bundle\exiftool*.exe") do ren "%%f" exiftool.exe
)

if not exist "exiftool_bundle\exiftool.exe" (
  echo ERROR: exiftool_bundle\exiftool.exe is missing.
  pause
  exit /b 1
)
echo exiftool ready: exiftool_bundle\exiftool.exe

echo.
echo === [5/5] Packaging with PyInstaller ===
set "ADD_BIN=exiftool_bundle\exiftool.exe;."
set "ADD_DATA="
if exist "exiftool_bundle\exiftool_files" set "ADD_DATA=--add-data exiftool_bundle\exiftool_files;exiftool_files"

pyinstaller --noconfirm --clean --onefile --windowed ^
  --name PhotoOrganizer ^
  --add-binary "%ADD_BIN%" ^
  %ADD_DATA% ^
  organize_photos_gui.py
if errorlevel 1 (
  echo PyInstaller failed.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo SUCCESS! Output: dist\PhotoOrganizer.exe
echo Just double-click it to run. No extra install needed.
echo ============================================================
pause
endlocal
