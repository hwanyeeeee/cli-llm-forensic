# 실측 — 원본 보존 · temp 작업 경로 · 소실(시간의존) 원리

날짜: 2026-06-17
측정 머신: 개발자 WSL2 Ubuntu (실데이터 `~/.claude`, `/tmp` = ext4 relatime).

> 이 문서는 **개발자 머신 실데이터로 직접 측정한 것만** 적는다. 추측·미검증 주장은 뺐다.
> 측정값(개수·구조·존재여부)만 적고 본문/시크릿은 노출하지 않는다.
> 팀원은 *자기 머신*에서 "검증 명령"을 돌려 교차확인한다 → n=2로 굳히기(논문 "n=1" 비판 방어).
> 시간의존(C)·환경의존(D)은 과장 없이 그대로 적는다.

---

## A. 원본 보존 — Claude가 자체 보관

사용자가 올리거나 편집한 파일의 **원본/이전 버전을 Claude Code가 `~/.claude` 안에 스스로 백업**한다. 디스크 복구(FAT32 carving) 없이도 상당 부분 복원이 여기서 나온다.

```
~/.claude/
├─ uploads/<sessionUUID>/<8hex>-<원본파일명>     ← 업로드/첨부 파일 원본 그대로
│     예: ecada9f2-…/3562e7fd-TalkFile_fig_storage.html
│         앞 8hex(3562e7fd) ≠ 파일 sha256(d9b386…) → 단순 sha256 아님(식별자, 해시방식 미상)
├─ file-history/<UUID>/<contenthash>@v<N>        ← 편집한 파일의 버전별 스냅샷
│     @v1=초기, @v2+=수정본   (실측 171MB, 93개 디렉토리)
└─ backups/.claude.json.backup.<epoch-ms>        ← 설정 파일 백업
```

- **원본↔백업 매핑은 transcript 안의 `file-history-snapshot` 레코드가 연결한다.** `~/.claude/projects/<폴더>/<세션>.jsonl` 의 한 줄:
  ```
  { "type":"file-history-snapshot", "messageId":…, "isSnapshotUpdate":…,
    "snapshot":{ "messageId":…, "timestamp":…, "trackedFileBackups":{ 원본경로 → 백업 } } }
  ```
  `trackedFileBackups` 가 **원본 디스크 경로 ↔ file-history 백업**을 잇는다. (실측: 레코드 7,980줄, snapshot 키 = `messageId`·`timestamp`·`trackedFileBackups`.)
- **`uploads` 앞 8hex는 단순 sha256이 아니다**(실측 불일치). 식별자일 뿐 — 무결성 대조용 해시로 쓰지 말 것. 해시방식은 미상.
- 검증 명령:
  ```bash
  du -sh ~/.claude/uploads ~/.claude/file-history ~/.claude/backups 2>/dev/null   # 크기
  find ~/.claude/file-history -maxdepth 1 -type d | wc -l                          # 스냅샷 디렉토리 수
  grep -rh 'file-history-snapshot' ~/.claude/projects 2>/dev/null | wc -l          # 매핑 레코드 수
  # 스냅샷 레코드 키 구조만 확인(값 노출 X):
  grep -rh 'file-history-snapshot' ~/.claude/projects 2>/dev/null | head -1 \
    | python3 -c "import sys,json; r=json.loads(sys.stdin.readline()); print(sorted(r['snapshot'].keys()))"
  ```
  내 결과: ____

## B. temp 작업 경로 — 에이전트 실행 부산물

`~/.claude`(기록)와 **별개로**, 에이전트가 명령·도구·서브에이전트를 돌리며 만든 임시 산물이 `/tmp` 에 쌓인다.

- **기본 경로 = `/tmp`** (실측 `TMPDIR` unset).
- `/tmp/claude-1000/<프로젝트경로인코딩>/<세션UUID>/tasks/<taskid>.output`
  → 백그라운드 명령·도구·서브에이전트 출력. **프로젝트별·세션별 분리.** (`claude-1000` 의 `1000` = uid.)
  서브에이전트 출력은 `~/.claude/projects/.../subagents/agent-<id>.jsonl` 로 symlink 된다.
  (실측: `tasks/` 디렉토리 33개, `.output` 파일 159개.)
- `~/.claude/shell-snapshots/snapshot-bash-<epoch>-<rand>.sh`
  → bash 도구 실행마다 셸 환경 스냅샷(약 139줄). (실측 53개 파일.)
- **`/tmp` 전체(실측 1.4GB)** 는 에이전트 작업 부산물이 누적된 보고: mktemp형 `tmpXXXXXXXX/` 200개, 테스트 잔재 `*test*/` 57개, 그 외 `.py`·`.png`·`.json/.jsonl` 등이 섞여 있다. **여러 프로젝트 흔적이 혼재**한다.
- 검증 명령:
  ```bash
  echo "TMPDIR=${TMPDIR:-<unset>}"
  ls -d /tmp/claude-1000 2>/dev/null && find /tmp/claude-1000 -name '*.output' | wc -l
  ls ~/.claude/shell-snapshots/ | wc -l
  du -sh /tmp 2>/dev/null
  find /tmp -maxdepth 1 -type d -name 'tmp*' | wc -l        # mktemp형
  find /tmp -maxdepth 1 -type d -iname '*test*' | wc -l     # 테스트 잔재
  ```
  내 결과: ____

> **주의(식별 휴리스틱)** — `/tmp` 는 전 프로세스 공용이라 "에이전트 것"만 골라내려면 휴리스틱이 필요하다: ① `/tmp/claude-<uid>/` 하위(확정), ② mktemp 패턴(`tmpXXXXXXXX`), ③ mtime 상관(세션 시각대), ④ 내용. 도구는 이 우선순위로 귀속한다.

## C. 보존/소실 — 시간의존 (정직하게)

`/tmp` 흔적은 **영구가 아니다**. 다만 "정확히 30일"도 아니다 — 정직하게 적는다.

- **`/tmp` = ext4 relatime** (tmpfs 아님). 실측: `/dev/sdd on / type ext4 (rw,relatime,…)`, `/tmp` 동일 마운트.
  → 재부팅 즉시휘발(tmpfs)은 **아니다**. 디스크에 남는다.
- **정리 타이머** `systemd-tmpfiles-clean.timer`: `OnBootSec=15min`, `OnUnitActiveSec=1d`
  → 부팅 15분 후 첫 실행, 이후 **하루마다** (Description "Daily Cleanup of Temporary Directories"). 실측 journal: 06-15·06-16 매일 실행·성공.
- **정책** `/usr/lib/tmpfiles.d/tmp.conf` 11행: `D /tmp 1777 root root 30d`
  → age **30일** 초과 항목 삭제. `D` 타입은 age 정리 + "부팅 시 디렉토리 내용 제거"를 함께 뜻한다.
- **age 판정 = atime·ctime·mtime 중 *가장 최근* 기준.** relatime이라 접근 시 atime이 갱신 → age가 리셋되어 보존이 연장될 수 있다(활발히 쓰는 파일은 안 지워지고, 방치분만 삭제). 즉 윈도우는 "마지막 접근 후 30일"에 가깝다.
- **`D`의 "부팅 시 비움"** 은 WSL `wsl --shutdown` 후 재가동에서 더 일찍 비울 수도 있으나, 이 머신 systemd가 **`degraded`** 상태라(실측) 실제 동작은 **환경의존**이다 — 일반화 금지.
- 현재 dry-run 삭제대상 0(전부 6일 이내, 가장 오래된 잔재 06-11~12 = 부팅일 이후).
- 검증 명령:
  ```bash
  findmnt -no FSTYPE,OPTIONS /tmp 2>/dev/null || mount | grep ' /tmp \| / '   # ext4 relatime 확인
  systemctl cat systemd-tmpfiles-clean.timer | grep -E 'OnBootSec|OnUnitActiveSec|Description'
  grep -nE '^[Dd] +/tmp ' /usr/lib/tmpfiles.d/tmp.conf                        # 30d 정책
  systemctl is-system-running                                                # degraded 여부
  systemd-tmpfiles --clean --dry-run 2>/dev/null | head                      # 지금 삭제대상(현재 0)
  ```
  내 결과: ____

> **결론(정직)**: `/tmp` 흔적은 **"정확히 30일"이 아니라 "최대 ~30일 보존 윈도우, 접근·재부팅·환경에 따라 변동"** 이다. 이는 `논문대비-신규발견.md §A`의 paste-cache 35% 소실과 같은 **시간의존 증거** — 사후조사 타이밍이 늦으면 `/tmp` 흔적은 이미 소실된다. **빠른 수집이 필수**이고, 복구(carving)는 별개 영역이다.

## D. 환경의존 — 일반화 금지

`/tmp` 내용도, 정리정책(systemd 활성도)도 **머신마다 다르다.**

- 특정 경로의 존재는 **설치물·사용 이력 의존**이다. 예: 이 머신의 `/tmp/.wsl-screenshot-cli` 는 *이 사용자가 설치한* WSL 스크린샷 데몬 산물 — **팀원 WSL엔 존재하지 않는다.** 즉 "이 경로가 있다"는 일반화하면 안 된다.
- 정리정책도 환경마다 다르다: 이 머신은 systemd가 `degraded` 라 타이머 동작이 보장되지 않는다. 다른 머신은 timer가 정상이거나, `tmp.conf` age가 다를 수 있다.
- → **도구는 환경의존을 가정하고 설계**하고, 팀원 머신 등 **n=2 교차확인**으로 굳힌다(`논문대비-신규발견.md §C "기능 의존"` 논리와 동일). **버전도 함께 기록**한다(`claude --version`).
- 검증 명령:
  ```bash
  claude --version                                   # 버전 핀
  ls -d /tmp/.wsl-screenshot-cli 2>/dev/null && echo "있음" || echo "없음(=이 환경 미설치)"
  ```
  내 결과: ____

---

## 포렌식 함의 (교수님 피드백 ①②와 연결)

| 피드백 | 어디서 나오나 | 디스크 복구(carving) 없이 가능? |
|---|---|---|
| ① 업로드 **원본 저장 위치** | `~/.claude/uploads/<sessionUUID>/<8hex>-<원본명>` (A) | 예 — Claude가 원본 그대로 보관 |
| ② 삭제·편집 전 **원본 복구** | `~/.claude/file-history/<UUID>/<contenthash>@v<N>` + transcript의 `file-history-snapshot` 매핑 (A) | 예 — 버전 스냅샷으로 상당부 복원 |

- **디스크 복구가 필요한 영역**: Claude가 추적하지 않은 **완전 외부삭제**(에이전트 밖에서 지운 파일)만 carving 대상이다. uploads/file-history로 덮이는 부분은 carving 없이 복원된다.
- **`/tmp`(B)** 는 ①②와 별개 — 에이전트 실행 *과정*의 산물(임시 처리공간·스크립트·도구/서브에이전트 출력)이다. "무엇을 어떻게 처리했나"의 흔적.
- **단, 셋 다 시간의존(C)·환경의존(D)** 이다. 원본 보존(A)도 file-history 보존 한도·외부삭제 여부에 따라, `/tmp`(B)도 ~30일 윈도우에 따라 소실될 수 있다. 발표·도구 모두 이 *시간 의존성*을 함께 명시한다(과장 방지).

## 주의
- 이 아티팩트·경로는 **버전 의존**(공식 API 계약 없음). 버전 함께 기록(`claude --version`).
- 자기 머신 점검 시 **본인 실데이터** → 값 출력 말고 *개수·구조·존재여부*만(시크릿 노출 주의).
