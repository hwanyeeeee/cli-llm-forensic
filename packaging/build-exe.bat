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

REM 2) Install / upgrade PyInstaller + pywebview (native GUI window)
echo [clfx] Installing/verifying PyInstaller + pywebview...
python -m pip install --quiet --upgrade pyinstaller pywebview
if errorlevel 1 (
  echo [ERROR] pyinstaller/pywebview install failed. Check network/permissions.
  pause
  exit /b 1
)

REM 3) Build single exe. --add-data separator on Windows is ; (source;dest).
REM    --collect-all webview bundles the pywebview GUI backend.
echo [clfx] Building (--onefile)...
python -m PyInstaller --onefile --name clfx --collect-all webview --add-data "clfx\web\static;clfx\web\static" packaging\launcher.py
if errorlevel 1 (
  echo [ERROR] build failed. See log above.
  pause
  exit /b 1
)

echo.
echo [clfx] Done. Output: %CD%\dist\clfx.exe
echo        Double-click clfx.exe to launch (native window with the scan screen; browser fallback).
pause
endlocal
