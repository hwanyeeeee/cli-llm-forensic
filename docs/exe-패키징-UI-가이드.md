# clfx exe 패키징 + UI 작업 가이드 (팀원 전달용)

날짜: 2026-06-17 · 대상: UI 담당 팀원 + 코어(엔진/패키징) 담당.
결정: 최종 배포 = **PyInstaller 단일 exe + 내장 웹서버**. 수사관이 exe 더블클릭 → 내장 서버 기동 → 브라우저 자동 오픈 → 대시보드.

---

## 1. 큰 그림

```
clfx.exe (PyInstaller --onefile)
 ├─ clfx 엔진 (parse/analyze/query) ── 결정적, 단일 진실원천
 ├─ 내장 http.server (clfx/web/server.py) ── /api/* 제공
 └─ static HTML/CSS/JS (clfx/web/static/) ── 화면  ← 팀원 작업 영역
실행 흐름: exe 실행 → serve 기동(127.0.0.1) → webbrowser 자동 오픈 → 대시보드 표시
```

- **UI는 HTML로 제작**(웹 기술 그대로). 네이티브 GUI 아님.
- exe 안에 서버+UI 다 들어가 단독 실행. 파이썬 설치 불필요.
- 입력 데이터 = `analyzed.jsonl`(parse→analyze 산출물). exe가 그걸 로드해 대시보드로 보여줌.

## 2. 역할 분담

| 담당 | 영역 | 파일 |
|---|---|---|
| **UI 팀원** | 화면(디자인·레이아웃·차트·UX) | `clfx/web/static/index.html`, `app.css`, `app.js` **만** |
| 코어 | 엔진·API·패키징 | `clfx/web/api.py`, `server.py`, `clfx/query/*`, PyInstaller spec |

**UI 팀원은 `clfx/web/static/` 3개 파일만 손댄다.** 엔진·API·서버는 건드리지 않는다. 새 데이터가 필요하면(예: 월별 집계, 키워드 빈도) 코어에 "이런 `/api/...` 엔드포인트 + JSON 형태 필요"라고 요청 → 코어가 엔진에서 계산해 제공 → UI는 받아서 그림.

## 3. UI ↔ 엔진 계약 (불변 원칙)

**엔진(`QueryEngine`)이 단일 진실원천. UI는 호출·표시만.** 검색·분석·탐지·집계 로직을 JS로 재구현하지 않는다(증거 분기 방지). 현재 계약:

- `GET /api/events` → `{events:[...], count}` — 전체 이벤트(ts 정렬). 초기 타임라인.
- `GET /api/query?q=<자연어>` → `{op, intent, events:[...], count, summary}` — 질의 결과.
- 각 event = `{ts, agent, session, actor, action, target, preview, tags[], source{file,line}}` (스키마: `docs/event-schema.md`).

**새 시각화(피드백 기능)가 필요로 할 신규 API** — 코어가 추가, UI는 소비:
- 월별 활동량 막대그래프 → `GET /api/activity?by=month` (예정)
- 키워드 빈도 파이 → `GET /api/keywords` (예정)
- 프롬프트 요약 → 기존 `/api/query`의 summarize 활용 또는 `/api/prompts/summary`
- (확정 형태는 피드백 spec에서 — `docs/superpowers/specs/`)

→ **UI는 차트 라이브러리로 이 JSON을 그리기만.** 집계 숫자는 엔진이 준다.

## 4. UI 팀원이 지금 할 수 있는 일

현재 `clfx/web/static/`는 동작하는 최소 UI(타임라인 actor 색구분·필터·질의박스·secret 뱃지·이벤트 클릭 상세). 여기서:

1. **디자인·레이아웃 개선** — 현재 기능 유지하며 보기 좋게.
2. **차트 영역 자리 잡기** — 월별 막대그래프/키워드 파이가 들어갈 컨테이너 + 차트 라이브러리 선택(아래 5절).
3. 기존 fetch 패턴(`app.js`의 `load()`) 따라 새 엔드포인트 연결(엔드포인트 준비되면).

**제약**: 외부 CDN 의존 주의 — exe는 오프라인 환경에서도 돌아야 한다. 차트 라이브러리는 **번들(static에 .js 동봉)**하거나 의존 없는 경량(직접 SVG/Canvas)으로. CDN `<script src=http...>`는 오프라인서 깨진다.

## 5. 차트 라이브러리 (오프라인 제약)

- **권장**: Chart.js나 uPlot의 .js 파일을 `clfx/web/static/`에 직접 동봉(CDN 아님) → exe 번들에 포함.
- 또는 의존 0: 막대/파이 정도는 vanilla JS + inline SVG로 충분(가장 가벼움, exe 크기↓).
- 결정은 UI 팀원 — 단 **CDN 링크 금지**(오프라인).

## 6. exe 패키징 (코어 담당)

PyInstaller `--onefile`. static을 데이터로 동봉.

```bash
pip install pyinstaller
pyinstaller --onefile \
  --name clfx \
  --add-data "clfx/web/static:clfx/web/static" \
  packaging/launcher.py
# 산출물: dist/clfx (또는 clfx.exe on Windows)
```

**코어가 처리할 코드 포인트**:
1. `packaging/launcher.py` 신규 — `analyzed.jsonl` 경로 인자(또는 파일 선택) 받아 `serve()` 기동 + `webbrowser.open(url)`. 인자 없으면 안내.
2. `clfx/web/server.py:13` `_STATIC = os.path.join(os.path.dirname(__file__), "static")` — **PyInstaller `--onefile`은 `sys._MEIPASS`에 압축 해제**하므로 그 환경에서도 static을 찾게 보정:
   ```python
   import sys, os
   _BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
   _STATIC = os.path.join(_BASE, "clfx", "web", "static")
   ```
   (frozen 아닐 때 = 기존 경로, frozen일 때 = _MEIPASS/clfx/web/static — `--add-data` 대상과 일치)
3. 포트 충돌 시 빈 포트 자동 선택(`port=0`) 후 실제 포트로 브라우저 오픈.

## 7. 검증

- 개발 중: `python3 -m clfx.cli serve analyzed.jsonl` (현행) — UI 작업은 이걸로 확인, exe 매번 안 빌드.
- 패키징 검증: `pyinstaller` 빌드 → `dist/clfx analyzed.jsonl` 실행 → 브라우저 대시보드 뜨고 `/api/events` 200 + static(HTML/CSS/JS) 정상 로드 확인.
- 오프라인 검증: 네트워크 끊고 exe 실행 → UI 깨짐 없는지(CDN 의존 없는지).

## 8. 흐름 요약 (수사관 사용)

```
1. clfx parse <대상 ~/.claude> -o events.jsonl        (또는 exe가 내부 수행 — 추후)
2. clfx analyze events.jsonl -o analyzed.jsonl
3. clfx.exe analyzed.jsonl   →  브라우저 대시보드 자동 오픈
```
(1·2를 exe가 한 번에 하도록 묶을지는 피드백 spec에서 결정.)
