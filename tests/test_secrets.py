from clfx.analyze.secrets import scan, mask
from tests.conftest import ENV_BODY, CONFIG_BODY, IDRSA_BODY, NPMRC_BODY, APP_BODY

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
    assert "sk_live_CLFXTEST001" not in masked
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
    assert any(f.kind == "openai_key" for f in scan("sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"))
    assert any(f.kind == "openai_key" for f in scan("sk-svc-1234567890abcdefghijklmnopqrstuv"))
