# 출력 레코드 형태 (Event)

파싱·분석 결과는 아래 한 가지 레코드로 정리한다. **한 줄 = 에이전트가 한 행동 하나.**

```jsonc
Event {
  "ts":       "시각 (UTC, ISO8601)",
  "agent":    "claude | codex | gemini",
  "session":  "세션 id",
  "actor":    "user | agent",                         // 사람이 입력했나, 에이전트가 알아서 했나
  "action":   "prompt | read | bash | write | paste | response",   // 무슨 행동
  "target":   "대상 (파일 경로 / 명령 / URL)",
  "preview":  "내용 미리보기 (시크릿은 가림)",
  "tags":     ["secret", "pii"],                      // 분석으로 붙는 표시 (없으면 빈 배열)
  "source":   { "file": "원본 jsonl 경로", "line": 42 }   // 증거 추적용
}
```

## 규칙

- 모든 Event는 `source` 로 **원본 파일·줄을 되짚을 수 있어야** 한다 (증거능력).
- 시크릿 값은 `preview` 에 그대로 넣지 말고 가린다 (예: `‹secret›`).
- 데이터셋 정답(`ground-truth`)도 이 형식의 `actor`·`action`·`target` 을 그대로 쓴다 → 도구 출력과 1:1 비교.
- 새 필드가 필요하면 이 파일을 고치고 PR로만 바꾼다 (다른 문서에 복제 금지).

> 지금은 이 정도면 충분하다. 인과 관계·복구 표시 같은 건 필요해질 때 추가한다.
