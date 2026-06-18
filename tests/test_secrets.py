from clfx.analyze.secrets import scan, mask, _PATTERNS, _GATES, Finding
from tests.conftest import ENV_BODY, CONFIG_BODY, IDRSA_BODY, NPMRC_BODY, APP_BODY


def _scan_no_prefilter(text):
    """레퍼런스 구현: 프리필터(_GATES) 없이 모든 regex를 무조건 실행하는 옛 방식 그대로.
    scan()의 게이트 적용 결과가 이것과 byte-identical 이어야 한다(거짓음성 0 증명)."""
    if not text:
        return []
    spans, out = [], []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            s, e = (m.span(m.lastindex) if m.lastindex else m.span())
            if any(not (e <= a or s >= b) for a, b in spans):
                continue
            spans.append((s, e))
            out.append(Finding(kind, m.group(m.lastindex) if m.lastindex else m.group(), s, e))
    return sorted(out, key=lambda f: f.start)


def _as_tuples(findings):
    return [(f.kind, f.value, f.start, f.end) for f in findings]

def test_detects_all_eight_across_files():
    found = []
    for body in (ENV_BODY, CONFIG_BODY, IDRSA_BODY, NPMRC_BODY):
        found += [f.kind for f in scan(body)]
    assert {"stripe","aws_key_id","aws_secret","db_password",
            "github_pat","openai_key","ssh_private_key","npm_token"} <= set(found)

def test_noise_has_no_secret():
    assert scan(APP_BODY) == []

def test_mask_hides_value():
    masked = mask(ENV_BODY, scan(ENV_BODY))
    assert "sk_live_" "CLFXTEST001" not in masked
    assert "‹secret›" in masked

def test_pii_email():
    assert any(f.kind == "email" for f in scan("contact a@b.com please"))

def test_db_password_word_boundary():
    # 계약: 키 이름이 정확히 password/passwd/pwd(접두 db_만) — 임의 접두 변수는 db_password 아님
    assert not any(f.kind == "db_password" for f in scan("user_password=val"))
    assert not any(f.kind == "db_password" for f in scan("secret_password=val"))
    assert not any(f.kind == "db_password" for f in scan("app_password=val"))
    assert any(f.kind == "db_password" for f in scan("password=realSecret123"))
    assert any(f.kind == "db_password" for f in scan("DB_PASSWORD=CLFXTEST004_db_p@ssw0rd"))

def test_db_password_ignores_code():
    # 공백 있는 코드 할당(함수호출·타입주석·숫자·lambda·변수참조)은 시크릿 아님 → 미탐
    for code in ("password = input('Enter password: ')",
                 "password: str = None",
                 "db_password: string;",
                 "password = 123",
                 "password = 3.14",
                 "pwd = 0",
                 "passwd = -42",
                 "password = lambda x: x+1",
                 "password=lambda x: x",          # 무공백이라도 값 뒤 코드 잔여 → 미탐
                 "password = get_secret()",
                 "password = some_var"):
        assert not any(f.kind == "db_password" for f in scan(code)), code

def test_db_password_detects_real_credentials():
    # .env 스타일(구분자 직후 값) + 따옴표 값은 탐지
    assert any(f.kind == "db_password" for f in scan("DB_PASSWORD=CLFXTEST004_db_p@ssw0rd"))
    assert any(f.kind == "db_password" for f in scan('password = "s3cr3t-value!"'))
    assert any(f.kind == "db_password" for f in scan("PASSWORD='hunter2hunter2'"))

def test_openai_key_with_hyphens():
    # 최신 OpenAI 키 형식 sk-proj-*, sk-svc-* (내부 하이픈) 탐지
    assert any(f.kind == "openai_key" for f in scan("sk-proj-" "abcdefghijklmnopqrstuvwxyz0123456789"))
    assert any(f.kind == "openai_key" for f in scan("sk-svc-" "1234567890abcdefghijklmnopqrstuv"))


# --- OPT-5: 리터럴 프리필터 무손실(거짓음성 0) 검증 ---

def test_db_password_is_never_gated():
    # 계약: db_password는 안전한 단일 앵커가 없어 절대 게이트하지 않는다(항상 regex 실행).
    assert "db_password" not in _GATES


def test_every_other_pattern_is_gated():
    # db_password를 제외한 8개 패턴은 모두 리터럴 앵커 게이트를 가진다.
    gated = set(_GATES)
    assert gated == {"ssh_private_key", "stripe", "aws_key_id", "github_pat",
                     "openai_key", "npm_token", "aws_secret", "email"}


def _lossless_battery():
    """conftest 본문 + 까다로운 edge case 모음.
    각 항목: scan(프리필터 적용) == _scan_no_prefilter(무조건) 가 정확히 같아야 한다."""
    cases = [
        # conftest 공유 본문
        ENV_BODY, CONFIG_BODY, IDRSA_BODY, NPMRC_BODY, APP_BODY,
        ENV_BODY + CONFIG_BODY + IDRSA_BODY + NPMRC_BODY + APP_BODY,  # 전부 한 문서에
        # 빈/공백
        "", " ", "\n\n", "no secrets here at all",
        # 앵커는 있으나 실제 매치는 없음(false-positive 방지 경로도 동일해야)
        "PRIVATE KEY but not a real one", "sk_live_short", "AKIAtooshort",
        "ghp_short", "sk-tooshort", "npm_short",
        "aws_secret_access_key but no value here", "@ alone", "plain@",
        # 대소문자 변형 — aws_secret은 (?i)라 모두 매치되어야 함(ci 게이트가 잡아야)
        "AWS_SECRET_ACCESS_KEY=CLFXTESTuppercaseSecretAbcdef0123456",
        "Aws_Secret_Access_Key=CLFXTESTmixedcaseSecretAbcdef0123456",
        "aws_secret_access_key=clfxtestlowercaseSecretAbcdef0123456",
        # ssh PRIVATE KEY는 대소문자 민감 — 소문자 'private key'는 매치 안 됨(게이트도 동일하게 skip)
        "-----begin openssh private key-----\nx\n-----end openssh private key-----",
        # 각 타입 진짜 시크릿
        "STRIPE=sk_live_" "CLFXTEST001FAKEabcdefghij0123",
        "AWS_ACCESS_KEY_ID=AKIA" "CLFXTEST00000002",
        "ghp_" "CLFXTEST005FAKEabcdefghijklmno012345",
        "sk-proj-" "abcdefghijklmnopqrstuvwxyz0123456789",
        "npm_" "CLFXTEST008FAKEabcdefghijklmno012345",
        "contact a@b.com please",
        "password=realSecret123",
        "DB_PASSWORD=CLFXTEST004_db_p@ssw0rd",
        'password = "s3cr3t-value!"',
        # db_password 코드 라인(미탐이 정답) — 게이트 없이도 같아야
        "password = input('Enter password: ')",
        "password = lambda x: x+1",
        "password = get_secret()",
        "user_password=val", "secret_password=val",
        # 혼합/근접 시크릿(겹침 해소 경로까지 동일한지)
        "email a@b.com and ghp_" "CLFXTEST005FAKEabcdefghijklmno012345 and sk_live_" "CLFXTEST001FAKEabc0123",
        "AKIA" "CLFXTEST00000002 next to AKIA" "CLFXTEST00000003",
        # email vs db_password 우선순위(@ 포함된 password 값)
        "DB_PASSWORD=p@ssw0rd@host\n",
        # 유니코드/멀티라인
        "비밀번호 password=한글섞인값123\n다음줄",
        "multi\nline\nsk_live_" "CLFXTEST001FAKEabcdefghij0123\nmore",
    ]
    return cases


def test_prefilter_lossless_vs_bruteforce():
    # 핵심 무손실 증명: 프리필터 적용 scan == 무조건 실행 레퍼런스, (kind,value,start,end) 정확 일치.
    for text in _lossless_battery():
        got = _as_tuples(scan(text))
        ref = _as_tuples(_scan_no_prefilter(text))
        assert got == ref, f"prefilter changed result for: {text!r}\n got={got}\n ref={ref}"


def test_prefilter_lossless_mask_identical():
    # 마스킹 결과도 동일해야(다운스트림 출력 무손실).
    for text in _lossless_battery():
        assert mask(text, scan(text)) == mask(text, _scan_no_prefilter(text)), text
