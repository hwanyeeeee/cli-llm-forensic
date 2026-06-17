@echo off
REM ============================================================
REM  clfx.exe 빌드 스크립트 (Windows 전용)
REM  - 이 파일을 더블클릭하거나 명령창에서 실행하세요.
REM  - 산출물: dist\clfx.exe  (인자 0 실행 → 브라우저 스캔 화면)
REM ============================================================
setlocal

REM 스크립트 위치(packaging\) 기준으로 repo 루트로 이동
cd /d "%~dp0.."
echo [clfx] repo root: %CD%

REM 1) python 확인
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python 을 찾을 수 없습니다. https://python.org 에서 설치 후 PATH에 추가하고 다시 실행하세요.
  pause
  exit /b 1
)

REM 2) PyInstaller 설치/업데이트
echo [clfx] PyInstaller 설치/확인 중...
python -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
  echo [ERROR] pyinstaller 설치 실패. 네트워크/권한을 확인하세요.
  pause
  exit /b 1
)

REM 3) 단일 exe 빌드
REM    --add-data 의 구분자는 Windows에서 ; (소스;대상). 정적파일을 exe 안에 동봉.
echo [clfx] 빌드 시작 (--onefile)...
python -m PyInstaller --onefile --name clfx ^
  --add-data "clfx\web\static;clfx\web\static" ^
  packaging\launcher.py
if errorlevel 1 (
  echo [ERROR] 빌드 실패. 위 로그를 확인하세요.
  pause
  exit /b 1
)

echo.
echo [clfx] 빌드 완료.  산출물: %CD%\dist\clfx.exe
echo        더블클릭하면 기본 브라우저가 열리고 스캔 화면이 표시됩니다.
echo        (분석할 .claude 소스를 선택 → 스캔 → 대시보드)
pause
endlocal
