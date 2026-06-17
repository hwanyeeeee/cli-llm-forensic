# LLM 파트 인계 문서 (담당자 인수용)

작성: 2026-06-18 · 대상: LLM 담당 팀원 · 작성: panel0(설계/리뷰)
관련: `docs/event-schema.md`(단일 진실원천), `clfx/query/llm.py`, `clfx/web/api.py`(query_payload), `clfx/web/server.py`(/api/query)

이 문서 하나로 LLM 파트 인수 가능하도록 작성했다. 현재 상태 + codex 리뷰 지적 7건 + 최우선 과제(모델 지시준수)를 담았다.

---

## 1. 설계 원칙 (절대 깨지면 안 됨)

- **증거 = 결정적 엔진**(`QueryEngine`, `clfx/query/engine.py`). 검색/집계/타임라인은 엔진이 단일 진실원천. **LLM 없이도 동작**.
- **LLM = 산문(요약/대화)만**. 사실 주장·증거는 엔진이 책임. LLM은 문장화만.
- **보안(하드 제약)**: 증거 프롬프트는 시크릿 포함 가능 → **외부 LLM 전송 절대 금지**. 로컬 ollama만(`127.0.0.1:11434`). preview의 `‹secret›`/`‹pii›`는 엔진에서 마스킹된 상태로만 LLM에 전달.
- **결정성(I2/I4)**: 같은 입력=같은 출력. 테스트는 ollama 비의존(`make_llm`을 `None`으로 monkeypatch → digest 강제).

## 2. 현재 흐름 (동작하는 것)

```
사용자 질의 → route_intent(q)            # 룰 기반 op 판정(who_did/secrets/on_date/timeline/search) + actor + 날짜(6/15 월-일) + summarize
            → engine.<op>(...)            # 결정적 검색 → events (증거)
            → _by_origins(res, origins)   # 소스 칩(windows/wsl) 체크된 origin만(답변 범위)
            → answer(q, res, llm)          # 비어있지 않으면 대화형 답
              · op=search & 결과 0건 → answer_overview(q, _by_origins(engine.events), llm)  # 막연한 질문→전체 행위 개요
            → summary{text, citations, mode, llm_error?}
```
- `OllamaLLM.complete(prompt, system=None)`: **POST /api/chat**(messages 포맷 → 모델 채팅 템플릿 적용). `message.content` 추출 → 비면 `thinking` 폴백 → 그래도 비면 진단 RuntimeError. `keep_alive:30m`, `num_predict:512`, `timeout:300`.
- `prewarm()`: 스캔 완료 시 백그라운드로 모델 미리 로드(콜드로드 제거). fire-and-forget.
- `mode`: `"llm"`(gemma 산문) / `"digest"`(폴백, 결정적 내용) / `"empty"`(근거 0건). UI는 digest일 때만 "(로컬 LLM 미연결 …)" + `llm_error` 표시.
- `_prompt_context(events)`: ≤60건이면 마스킹 preview 포함 전량, >60이면 [집계 헤더]+표본 60(컨텍스트/타임아웃 bound). citations는 전량(무손실).
- `answer/summarize/answer_overview`: system(역할·규칙: 한국어 서술형·목록금지·지시반복금지·A=사용자/B=에이전트·(파일:줄) 인용) ↔ user(질문·데이터) 분리.

## 3. ★최우선 과제: 모델 지시준수 (실사용 핵심)

`gemma4:12b`가 **한국어 서술형 지시를 잘 안 따른다**: 프롬프트를 영어로 echo하거나 목록으로 나열한 사례 있음(batch9 system/user 분리로 완화 시도). 검증 필요:
- 재빌드 후 `6/16 요약` → 한국어 서술형 문단이 안정적으로 나오는지.
- 안 되면: (a) 더 강한 instruct 모델로 교체(예: 한국어 잘하는 모델), (b) few-shot 예시 추가, (c) `options`에 `temperature` 낮춤/`stop` 추가. 모델 교체는 `OllamaLLM(model=...)` 한 곳.
- 사용자 보유 모델: `gemma4:12b`(7.6GB), `gemma4:e2b`(7.2GB).

## 4. codex 리뷰 지적 7건 (= 작업 항목, 우선순위순)

**P0 (포렌식 무결성 — 반드시):**
1. `llm.py` answer/overview: LLM 산문에 **허위 인라인 인용**((fake.jsonl:999))이 섞일 수 있음. 산문 내 `(파일:줄)` 토큰을 결정적 `citations` 집합과 대조 → 불일치 토큰 제거 또는 digest 폴백.
2. `llm.py:_overview_context`: answer_overview `citations`가 **source(file:line)가 아니라 target 파일명**. "모든 답변 source 추적" 계약 위반 → 대표 Event의 `source.file:source.line`를 citations에 넣어라(top_files는 본문 근거로만).
3. `llm.py` OllamaLLM/prewarm: `host`가 **임의 URL 허용** → 원격 ollama로 증거 전송 위험(보안 하드제약 위반). 생성자에서 host를 `localhost`/`127.0.0.1`만 allowlist 검증, 그 외 거부.

**P1 (소스 필터 정확성):**
4. `api.py:_by_origins`: `origins=None`과 **빈 set을 모두 전체로 처리** → "소스 0개 선택"이 전체 답변이 됨. None만 전체, 빈 set은 `[]` 반환. server는 빈 sources를 빈 set으로 전달(현재 `or None`이라 빈→None).
5. `api.py:_by_origins`: **미태깅 이벤트가 non-empty origins 필터를 통과**(선택 안 한 출처 혼입 여지). LIVE 스캔은 전부 origin 태깅이라 실질 무영향이나, origins 지정 시 `_origin_of(e) in origins`만 통과하도록 엄격화 권장.

**P2 (일관성):**
6. `llm.py:summarize`: `summarize([], llm=...)`가 **빈 근거에도 `llm.complete` 호출** 가능(answer엔 빈 가드 있음). events 비면 즉시 `mode=empty`/digest 반환. (현재 query_payload는 summarize 미사용 — answer/overview만 씀. 그래도 방어.)

**설계 확인(버그 아님):**
7. `api.py:69` 빈 search→answer_overview: codex는 "무근거 질의도 LLM 답"이라 지적하나, **사용자 요구사항**("모든 질의에 gemma4 답변, 같은 정황 찾아줘")에 따른 의도된 동작. overview는 결정적 집계 근거라 날조 아님. 다만 무의미 토큰("asdfqwer")도 전체 개요를 받는 게 어색하면 **개요형 intent를 별도 라우팅**(예: "주로/요약/개요" 키워드)하고 그 외 빈 search는 `mode=empty`로 두는 방안 고려.

## 5. 테스트 / 검증

- `python -m pytest -q tests/test_query_llm.py tests/test_llm_ollama.py tests/test_web_api.py` (LLM 관련 회귀).
- 패턴: `monkeypatch.setattr(api,"make_llm",lambda *a,**k:None)` → ollama 비의존 결정적(digest). 실제 ollama 검증은 `clfx serve` 후 브라우저 코파일럿.
- 무손실: summary 변경이 `citations` 수(=증거 수)를 줄이면 안 됨.

## 6. 손대면 안 되는 것

- 엔진(`engine.py`)·파서·attribution은 LLM 파트 아님(증거 계층). LLM은 `llm.py` + `api.py`의 `query_payload`/`_by_origins` + `server.py`의 `/api/query`만.
- Event 스키마는 `docs/event-schema.md`에서만 변경(복제 금지).
