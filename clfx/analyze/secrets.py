import re
from dataclasses import dataclass


@dataclass
class Finding:
    kind: str
    value: str
    start: int
    end: int


# 강한/긴 패턴 우선(_PATTERNS 순서로 겹침 해소). email은 db_password보다 앞 → email 우선.
_PATTERNS = [
    ("ssh_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("stripe",          re.compile(r"sk_live_[A-Za-z0-9]{16,}")),
    ("aws_key_id",      re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_pat",      re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai_key",      re.compile(r"sk-[A-Za-z0-9-]{20,}")),   # sk-proj-*, sk-svc- 내부 하이픈 포함
    ("npm_token",       re.compile(r"npm_[A-Za-z0-9]{20,}")),
    ("aws_secret",      re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{16,})")),
    ("email",           re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # db_password: 키 이름이 정확히 password/passwd/pwd(접두 db_ 허용)인 할당만.
    #  - 앞 단어경계(lookbehind)로 user_password·secret_password 등 임의 접두 변수 배제.
    #  - 값은 (a)따옴표로 감싼 문자열 또는 (b).env 스타일(=/: 직후 공백 없이 시작)만 인정.
    #    코드 할당은 보통 '= ' 처럼 공백을 두므로(숫자·lambda·함수호출·변수참조) 전부 미탐 → 코드 라인 배제.
    ("db_password",     re.compile(
        r"(?i)(?<![A-Za-z0-9_-])(?:db[_-]?)?(?:password|passwd|pwd)\s*[=:]"
        r"(?:\s*['\"]([^'\"\n]+)['\"]"            # (a) 따옴표 값
        r"|(?=\S)([^\s'\";]+)(?=[ \t]*(?:\n|$)))")),  # (b) .env 스타일: 구분자 직후~줄 끝(값 뒤 코드 잔여 없음)
]


# 리터럴 프리필터(OPT-5): 각 패턴이 매치되려면 반드시 존재해야 하는 고정 리터럴 앵커.
#   앵커가 text에 없으면 regex는 절대 매치 불가 → finditer 호출을 건너뛴다(거짓음성 0).
#   앵커는 패턴의 대소문자 민감도와 동일하게 비교한다.
#   - aws_secret 은 (?i)로 키 이름이 대소문자 무시 → 앵커도 대소문자 무시(text.lower() 비교).
#   - db_password 는 안전한 단일 리터럴 앵커가 없다(password/passwd/pwd, 선택적 db_ 접두).
#     → GATE 제외: 항상 regex 실행(안전 우선, 절대 게이트하지 않음).
def _ci_anchor(anchor):
    """대소문자 무시 앵커: text.lower()에 lower(anchor)가 포함되는지."""
    lo = anchor.lower()
    return lambda text: lo in text.lower()


def _cs_anchor(anchor):
    """대소문자 민감 앵커: text에 anchor가 그대로 포함되는지."""
    return lambda text: anchor in text


# kind -> 게이트 함수(text를 받아 패턴 실행 여부 bool 반환). db_password는 의도적으로 미등록(항상 실행).
_GATES = {
    "ssh_private_key": _cs_anchor("PRIVATE KEY"),
    "stripe":          _cs_anchor("sk_live_"),
    "aws_key_id":      _cs_anchor("AKIA"),
    "github_pat":      _cs_anchor("ghp_"),
    "openai_key":      _cs_anchor("sk-"),
    "npm_token":       _cs_anchor("npm_"),
    "aws_secret":      _ci_anchor("aws_secret_access_key"),
    "email":           _cs_anchor("@"),
}


def scan(text):
    """겹치지 않는 탐지 결과(강/긴 패턴 우선). 캡처그룹 있으면 그 값, 없으면 전체 매치.
    각 regex 실행 전 _GATES의 리터럴 앵커 프리필터를 적용한다(앵커 부재 시 매치 불가능 → skip).
    db_password는 안전한 단일 앵커가 없어 게이트하지 않고 항상 실행한다(거짓음성 0 보장)."""
    if not text:
        return []
    spans = []
    out = []
    for kind, rx in _PATTERNS:
        gate = _GATES.get(kind)
        if gate is not None and not gate(text):   # 앵커 부재 → regex 매치 불가 → skip
            continue
        for m in rx.finditer(text):
            s, e = (m.span(m.lastindex) if m.lastindex else m.span())
            if any(not (e <= a or s >= b) for a, b in spans):   # 이미 잡힌 구간과 겹치면 skip
                continue
            spans.append((s, e))
            out.append(Finding(kind, m.group(m.lastindex) if m.lastindex else m.group(), s, e))
    return sorted(out, key=lambda f: f.start)


def mask(text, findings):
    """findings 의 값 구간을 ‹secret› 마커로 치환."""
    if not findings:
        return text
    res, last = [], 0
    for f in sorted(findings, key=lambda f: f.start):
        res.append(text[last:f.start])
        res.append("‹secret›")
        last = f.end
    res.append(text[last:])
    return "".join(res)
