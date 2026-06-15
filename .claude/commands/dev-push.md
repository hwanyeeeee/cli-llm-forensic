---
description: 현재 프로젝트의 managed 파일 1개를 Dev-harness로 push
argument-hint: <relative-path>
allowed-tools: Bash
---

현 프로젝트의 managed 파일 한 개를 하네스 측에 덮어쓴다. `$1`은 dev-sync.sh PATHS에 등록된 상대경로여야 한다 (예: `.claude/bin/send-to-pane.sh`).

```bash
bash .claude/bin/dev-sync.sh push "$1"
```

결과 그대로 보고. 다른 파생 프로젝트들은 다음 세션 시작 시 drift 감지로 자동 알림 받음.
