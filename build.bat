@echo off
REM ============================================================
REM   照片整理器 Windows 打包脚本
REM   在 Windows 10+ 上双击运行，输出 dist\PhotoOrganizer.exe
REM   要求：Python 3.10+ 已安装并在 PATH 中
REM ============================================================
setlocal enableextensions

cd /d "%~dp0"
echo.
echo === [1/5] 检查 Python ===
where python >nul 2>nul
if errorlevel 1 (
  echo 错误: 未找到 python.exe。请先安装 Python 3.10+ 并勾选 "Add to PATH"。
  echo 下载: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
python --version

echo.
echo === [2/5] 创建虚拟环境 .venv ===
if not exist .venv (
  python -m venv .venv || (echo 创建 venv 失败 & pause & exit /b 1)
)
call .venv\Scripts\activate.bat || (echo 激活 venv 失败 & pause & exit /b 1)

echo.
echo === [3/5] 安装依赖 ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller || (echo 装依赖失败 & pause & exit /b 1)

echo.
echo === [4/5] 准备 exiftool.exe ===
set "EXIFTOOL_VER=13.55"
set "EXIFTOOL_ZIP=exiftool-%EXIFTOOL_VER%_64.zip"
set "EXIFTOOL_URL=https://exiftool.org/%EXIFTOOL_ZIP%"

if not exist "exiftool_bundle\exiftool.exe" (
  echo 未发现 exiftool，正在下载 %EXIFTOOL_URL% ...
  if exist "%EXIFTOOL_ZIP%" del "%EXIFTOOL_ZIP%"
  powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%EXIFTOOL_URL%' -OutFile '%EXIFTOOL_ZIP%' -UseBasicParsing } catch { Write-Host $_; exit 1 }" || (
    echo 下载 exiftool 失败。请手动从 https://exiftool.org 下载 Windows 版，
    echo 解压后把 exiftool.exe 和 exiftool_files 目录放到 exiftool_bundle\ 下。
    pause
    exit /b 1
  )
  if exist exiftool_bundle rmdir /s /q exiftool_bundle
  powershell -NoProfile -Command "Expand-Archive -Force '%EXIFTOOL_ZIP%' -DestinationPath exiftool_bundle" || (echo 解压失败 & pause & exit /b 1)
  del "%EXIFTOOL_ZIP%"
  REM exiftool 的 Windows 包里主程序名为 "exiftool(-k).exe"，需要改名
  for %%f in ("exiftool_bundle\exiftool*.exe") do ren "%%f" exiftool.exe
)

if not exist "exiftool_bundle\exiftool.exe" (
  echo 错误: exiftool_bundle\exiftool.exe 未就绪，无法继续。
  pause
  exit /b 1
)
echo exiftool 已就绪: exiftool_bundle\exiftool.exe

echo.
echo === [5/5] 用 PyInstaller 打包 ===
REM 注意 --add-binary / --add-data 在 Windows 上分隔符是 ";"
REM --windowed 让双击 .exe 时不弹黑色命令行窗口
set "ADD_BIN=exiftool_bundle\exiftool.exe;."
set "ADD_DATA="
if exist "exiftool_bundle\exiftool_files" set "ADD_DATA=--add-data exiftool_bundle\exiftool_files;exiftool_files"

pyinstaller --noconfirm --clean --onefile --windowed ^
  --name PhotoOrganizer ^
  --add-binary "%ADD_BIN%" ^
  %ADD_DATA% ^
  organize_photos_gui.py || (echo PyInstaller 失败 & pause & exit /b 1)

echo.
echo ============================================================
echo 构建成功！输出: dist\PhotoOrganizer.exe
echo 双击即可运行，无需额外安装。
echo ============================================================
pause
endlocal
