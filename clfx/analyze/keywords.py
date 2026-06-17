"""키워드 빈도 분석(결정적, 의존성0). 증거 집계 — 엔진이 진실원천.
한국어 형태소기 미사용(stdlib only) → 토큰 빈도 + 수사사전 매칭 + 시점 패턴."""
import re
from collections import Counter, defaultdict

from clfx.event import norm_ts

# 마스킹 마커 스팬(‹secret›·‹pii› 등) — 토큰화 전 통째 제거. 마커 내부 단어가 키워드로 새면 안 됨(redaction 마커를 데이터로 오인 + secret 강조 금지).
_MASK_SPAN = re.compile(r"‹[^›]*›")

# 수사 관점 위험 키워드(한국어+영어). 매칭되면 investigative=True 강조.
INVESTIGATIVE = {
    "비밀번호", "패스워드", "password", "주민", "주민등록", "계좌", "카드번호",
    "유출", "해킹", "공격", "탈취", "권한", "루트", "root", "sudo", "토큰", "token",
    "api", "key", "credential", "계정", "로그인", "개인정보", "기밀", "secret", "유출됨",
}
# 불용어(조사·관사·일반어). 한국어 정밀도 한계는 spec §6에 명시됨.
# 키워드-추출-개선안.md §3.② 반영 — 코드토큰·시스템경로어·한국어 일반어 확장(for/mnt/user 노이즈 제거).
_STOP = {
    "그", "이", "저", "것", "수", "등", "및", "the", "a", "an", "of", "to", "in",
    "is", "and", "or", "에", "는", "은", "이", "가", "을", "를", "도", "로", "으로",
    # 코드 토큰
    "for", "if", "else", "def", "return", "import", "class", "true", "false", "null",
    "var", "let", "const", "function", "async", "await", "print", "echo", "from", "as",
    "self", "none", "int", "str", "with", "not", "elif", "try", "except",
    # 시스템/경로어
    "mnt", "home", "usr", "tmp", "user", "opt", "etc", "bin", "root", "proc", "dev",
    "lib", "local", "users",
    # 한국어 일반어/지시어
    "이거", "그거", "저거", "해줘", "줘", "좀", "그리고", "그런데", "했어", "봐줘",
    "만들어", "알려줘", "보여줘", "이런", "저런", "해", "돼", "된", "거", "게",
}
_TOKEN = re.compile(r"[A-Za-z0-9_]+|[가-힣]+")

# 한국어 조사 경량 분리(형태소기 미사용). 어간<2자면 미분리(과분리 방지). 긴 조사 우선 매칭.
_PARTICLES = (
    "으로서", "으로써", "에게서",
    "으로", "에서", "에게", "한테", "께서", "처럼", "보다", "까지", "부터", "마다", "조차", "마저",
    "을", "를", "이", "가", "은", "는", "에", "의", "도", "로", "와", "과", "만", "랑",
)
_HANGUL = re.compile(r"^[가-힣]+$")


def _strip_particle(t):
    if not _HANGUL.match(t):           # 한글 토큰만(영문/숫자 토큰 무수정)
        return t
    for p in _PARTICLES:               # 긴 조사 먼저
        if t.endswith(p) and len(t) - len(p) >= 2:
            return t[: len(t) - len(p)]
    return t


def _tokens(text):
    out = []
    for t in _TOKEN.findall(text or ""):
        t = _strip_particle(t)         # 조사 분리 후 stopword/길이 검사(병합·수사사전 매칭 위해)
        tl = t.lower()
        if len(t) < 2 or tl in _STOP:
            continue
        out.append(t)
    return out


def keyword_stats(events, top=50, min_count=2):
    """대화 텍스트(action: prompt/response)의 preview에서 키워드 빈도·actor분리·수사플래그·시점패턴 집계.
    read/bash/paste(파일내용·명령·경로)는 제외 — for/mnt/user 노이즈 원천 차단(키워드-추출-개선안.md §3.①).
    min_count 미만(1회성) 토큰은 컷(§3.③). 증거(이벤트)는 전량 유지 — 차트 입력만 정제(무손실).
    반환: {"keywords": [{term,count,by_actor,investigative,pattern,days,by_day}, ...]}"""
    count = Counter()
    by_actor = defaultdict(lambda: {"user": 0, "agent": 0})
    by_day = defaultdict(Counter)            # term -> {day: n}
    for e in events:
        if e.action not in ("prompt", "response"):   # 대화 텍스트만(코드/경로/명령 노이즈 제외)
            continue
        text = _MASK_SPAN.sub(" ", e.preview or "")  # 대화 텍스트=preview(target은 빈문자). ‹secret›·‹pii› 마커 제거.
        day = (norm_ts(e.ts) or "")[:10] or "unknown"   # int epoch-ms도 ISO Z로 통일 → 슬라이스 TypeError 방지
        seen = list(dict.fromkeys(_tokens(text)))   # 결정적 dedup(첫 등장 순서 보존, set 순회 비결정성 제거)
        for term in seen:
            count[term] += 1
            actor = e.actor if e.actor in ("user", "agent") else "user"
            by_actor[term][actor] += 1
            by_day[term][day] += 1
    kws = []
    # 결정적 정렬: count 내림차순 + term 사전순 tie-break(동점 키워드 순서 PYTHONHASHSEED 무관).
    for term, c in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
        if c < min_count:                    # 1회성 토큰 컷(상위 top 안에서 적용 → 결과가 top보다 적을 수 있음·정상)
            continue
        days = by_day[term]
        # 집중형: 한 날이 전체의 절반 이상. 지속형: 분산. (단일 등장은 집중형.)
        pattern = "집중형" if max(days.values()) / sum(days.values()) >= 0.5 else "지속형"
        kws.append({
            "term": term, "count": c, "by_actor": dict(by_actor[term]),
            "investigative": term.lower() in {w.lower() for w in INVESTIGATIVE},
            "pattern": pattern, "days": len(days),
            # 일자별 분포(엔진 단일진실) — UI 팝업이 이걸 그린다(JS substring 재매칭 금지).
            "by_day": dict(sorted(days.items())),
        })
    return {"keywords": kws}
