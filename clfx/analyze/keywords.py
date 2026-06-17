"""키워드 빈도 분석(결정적, 의존성0). 증거 집계 — 엔진이 진실원천.
한국어 형태소기 미사용(stdlib only) → 토큰 빈도 + 수사사전 매칭 + 시점 패턴."""
import math
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
        if len(t) < 2 or tl in _STOP or t.isdigit():   # 순수 숫자(2026 등) 컷 — 의미 없는 연도/수치 노이즈
            continue
        out.append(t)
    return out


def keyword_stats(events, top=50, min_count=2):
    """대화(prompt/response) preview에서 TF-IDF로 변별적 키워드 추출(실무 e-discovery 표준).
    문서=세션(e.session). df=term 등장 세션 수, idf=ln((1+N)/(1+df))+1(sklearn 평활), score=count×idf.
    흔한 토큰(거의 모든 세션 등장 — observation/tool/this 등)은 idf↓로 강등, 드문 수사어는 상위.
    read/bash/paste(파일내용·명령·경로)는 제외(for/mnt/user 노이즈 원천 차단). min_count 미만은 컷. 결정적.
    증거(이벤트)는 전량 유지 — 차트 입력/랭킹만 정제(무손실).
    반환: {"keywords": [{term,count,by_actor,investigative,pattern,days,by_day,score}, ...]}"""
    count = Counter()
    by_actor = defaultdict(lambda: {"user": 0, "agent": 0})
    by_day = defaultdict(Counter)            # term -> {day: n}
    doc_terms = defaultdict(set)             # session -> set(terms) (df 계산용)
    sessions = set()
    for e in events:
        if e.action not in ("prompt", "response"):   # 대화 텍스트만(코드/경로/명령 노이즈 제외)
            continue
        sess = e.session or "?"
        sessions.add(sess)
        text = _MASK_SPAN.sub(" ", e.preview or "")  # 대화 텍스트=preview(target은 빈문자). ‹secret›·‹pii› 마커 제거.
        day = (norm_ts(e.ts) or "")[:10] or "unknown"   # int epoch-ms도 ISO Z로 통일 → 슬라이스 TypeError 방지
        seen = list(dict.fromkeys(_tokens(text)))   # 결정적 dedup(첫 등장 순서 보존, set 순회 비결정성 제거)
        for term in seen:
            count[term] += 1
            actor = e.actor if e.actor in ("user", "agent") else "user"
            by_actor[term][actor] += 1
            by_day[term][day] += 1
            doc_terms[sess].add(term)
    df = Counter()                           # term -> 등장 세션 수
    for terms in doc_terms.values():
        for term in terms:
            df[term] += 1
    n_docs = max(len(sessions), 1)

    def _score(term):
        idf = math.log((1 + n_docs) / (1 + df[term])) + 1   # sklearn 평활 — 단일세션도 idf>0
        return count[term] * idf

    cand = [t for t, c in count.items() if c >= min_count]   # 1회성 컷
    # 결정적 정렬: TF-IDF 점수 내림차순 + term 사전순 tie-break(PYTHONHASHSEED 무관).
    cand.sort(key=lambda t: (-_score(t), t))
    kws = []
    for term in cand[:top]:
        days = by_day[term]
        # 집중형: 한 날이 전체의 절반 이상. 지속형: 분산. (단일 등장은 집중형.)
        pattern = "집중형" if max(days.values()) / sum(days.values()) >= 0.5 else "지속형"
        kws.append({
            "term": term, "count": count[term], "by_actor": dict(by_actor[term]),
            "investigative": term.lower() in {w.lower() for w in INVESTIGATIVE},
            "pattern": pattern, "days": len(days),
            # 일자별 분포(엔진 단일진실) — UI 팝업이 이걸 그린다(JS substring 재매칭 금지).
            "by_day": dict(sorted(days.items())),
            "score": round(_score(term), 3),   # 정렬 근거(디버그) — UI 무시 가능
        })
    return {"keywords": kws}
