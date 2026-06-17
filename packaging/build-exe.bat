@echo off
REM ============================================================
REM  clfx.exe build script (Windows)
REM  - Double-click this file, or run from cmd.
REM  - Output: dist\clfx.exe  (run with no args -> native window; browser fallback)
REM ============================================================
setlocal

REM Move to repo root (this script lives in packaging\)
cd /d "%~dp0.."
echo [clfx] repo root: %CD%

REM 1) Check python
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found. Install from https://python.org and enable "Add to PATH", then retry.
  pause
  exit /b 1
)

REM 2a) Kill any running instance (locked exe cannot be overwritten)
taskkill /im clfx.exe /f >nul 2>nul

REM 2b) Clean previous build artifacts (stale cache can bundle old static files)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist clfx.spec del /q clfx.spec

REM 3) Install / upgrade PyInstaller + pywebview (native GUI window)
echo [clfx] Installing/verifying PyInstaller + pywebview...
python -m pip install --quiet --upgrade pyinstaller pywebview
if errorlevel 1 (
  echo [ERROR] pyinstaller/pywebview install failed. Check network/permissions.
  pause
  exit /b 1
)

REM 4) Build single exe. --add-data separator on Windows is ; (source;dest).
REM    --collect-all webview bundles the pywebview GUI backend.
REM    --noconfirm overwrites prior output without an interactive prompt.
echo [clfx] Building (--onefile)...
python -m PyInstaller --noconfirm --onefile --name clfx --collect-all webview --add-data "clfx\web\static;clfx\web\static" packaging\launcher.py
if errorlevel 1 (
  echo [ERROR] build failed. See log above.
  pause
  exit /b 1
)

if not exist "dist\clfx.exe" (
  echo [ERROR] dist\clfx.exe not produced. See log above.
  pause
  exit /b 1
)
echo.
echo [clfx] Done. Output: %CD%\dist\clfx.exe
echo [clfx] Built artifact:
dir "dist\clfx.exe" | findstr clfx.exe
echo        Double-click clfx.exe to launch (native window with the scan screen; browser fallback).
pause
endlocal
