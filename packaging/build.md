# clfx.exe 빌드 (PyInstaller)

Windows에서 빌드(타깃이 Windows exe).

## 쉬운 방법 — 배치 스크립트

`packaging\build-exe.bat` 을 **더블클릭**하거나 명령창에서 실행한다.
(repo 루트로 자동 이동 → python 확인 → pyinstaller+pywebview 설치 → 빌드 → `dist\clfx.exe`)

## 수동

리포 루트에서:

    pip install pyinstaller pywebview
    pyinstaller --onefile --name clfx --collect-all webview ^
      --add-data "clfx\web\static;clfx\web\static" ^
      packaging\launcher.py

- 산출물: `dist\clfx.exe`
- `--add-data` 구분자: **Windows는 `;`**, Unix/WSL은 `:`.
- 정적파일은 import가 아니라 데이터라 `--add-data`로 동봉 → 실행 시 `sys._MEIPASS/clfx/web/static`에 풀림(server._static_dir이 처리).
- `--collect-all webview`: pywebview GUI 백엔드(Windows=내장 Edge WebView2) 동봉.
- 실행: `clfx.exe` → 네이티브 GUI 창에 스캔 화면 → 소스 선택 → 대시보드. **GUI 백엔드 없으면 기본 브라우저로 폴백.**
