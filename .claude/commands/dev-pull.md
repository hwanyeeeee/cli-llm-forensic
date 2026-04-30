---
description: Pull managed files from Dev-harness into current project (overwrite)
allowed-tools: Bash
---

하네스의 managed 인프라 파일을 현 프로젝트에 일괄 덮어쓴다. 하네스 본체에서 호출 시 자기 자신과 비교해 모두 in sync로 나옴.

```bash
bash .claude/bin/dev-sync.sh pull
```

결과 출력 그대로 사용자에게 보고하고 턴 마쳐라.
