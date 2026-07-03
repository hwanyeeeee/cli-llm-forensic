# AgenTrace.exe 빌드 (PyInstaller)

Windows에서 빌드(타깃이 Windows exe).

## 쉬운 방법 — 배치 스크립트

`packaging\build-exe.bat` 을 **더블클릭**하거나 명령창에서 실행한다.
(repo 루트로 자동 이동 → python 확인 → pyinstaller+pywebview 설치 → 빌드 → `dist\AgenTrace.exe`)

## 수동

리포 루트에서:

    pip install pyinstaller pywebview
    pyinstaller --onefile --name AgenTrace --collect-all webview ^
      --add-data "clfx\web\static;clfx\web\static" ^
      packaging\launcher.py

- 산출물: `dist\AgenTrace.exe`
- `--add-data` 구분자: **Windows는 `;`**, Unix/WSL은 `:`.
- 정적파일은 import가 아니라 데이터라 `--add-data`로 동봉 → 실행 시 `sys._MEIPASS/clfx/web/static`에 풀림(server._static_dir이 처리).
- `--collect-all webview`: pywebview GUI 백엔드(Windows=내장 Edge WebView2) 동봉.
- 실행: `AgenTrace.exe` → 네이티브 GUI 창에 스캔 화면 → 소스 선택 → 대시보드. **GUI 백엔드 없으면 기본 브라우저로 폴백.**

## WSL-side 파싱 위임 (O11)

- exe는 `--add-data "clfx;clfx_src"`로 clfx 소스(.py)를 동봉한다 — `\\wsl.localhost` 소스 선택 시
  wsl.exe interop으로 WSL 내부에서 헬퍼(`clfx.wsl_helper`)를 실행해 9P를 우회한다(빠르고 wedge 내성).
- 실패(wsl.exe/python3 부재 등) 시 자동으로 기존 UNC 직접 파싱 폴백 + attestation에 사유 표면화.
- 증거 환경 내 발자국: `python3 -B -E -s`(pyc 생성 0), 읽기는 jsonl뿐(read-only 강제), 쓰기는 Windows
  임시 디렉터리의 출력 파일뿐. 스테이징된 헬퍼의 SHA-256이 attestation `delegate.helper_sha256`에 기록됨.
- 강제 비활성: 환경변수 `CLFX_NO_DELEGATE=1`.
