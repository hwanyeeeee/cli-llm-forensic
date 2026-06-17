from clfx.event import Event, Source
from clfx.analyze.keywords import keyword_stats


def _ev(actor, target, preview, ts):
    return Event(ts=ts, agent="claude", session="s", actor=actor, action="read",
                 target=target, preview=preview, source=Source("h.jsonl", 1), tags=[])


def test_frequency_and_actor_split():
    evs = [
        _ev("user", "a.py", "비밀번호 유출 확인", "2026-06-11T01:00:00.000Z"),
        _ev("agent", "b.py", "비밀번호 점검", "2026-06-11T02:00:00.000Z"),
        _ev("user", "c.py", "일반 코드 리뷰", "2026-06-11T03:00:00.000Z"),
    ]
    st = keyword_stats(evs)
    kws = {k["term"]: k for k in st["keywords"]}
    # "비밀번호" 3회 등장 안 됨 — 2건(user1/agent1). actor 분리.
    assert kws["비밀번호"]["count"] == 2
    assert kws["비밀번호"]["by_actor"] == {"user": 1, "agent": 1}
    # 수사 위험키워드 플래그
    assert kws["비밀번호"]["investigative"] is True
    assert kws["유출"]["investigative"] is True


def test_concentration_pattern():
    # 같은 키워드가 하루 몰림 → 집중형, 여러 날 분산 → 지속형
    same_day = [_ev("user", "x", "해킹 시도", f"2026-06-11T0{i}:00:00.000Z") for i in range(1, 5)]
    st = keyword_stats(same_day)
    hk = {k["term"]: k for k in st["keywords"]}["해킹"]
    assert hk["pattern"] == "집중형"

    spread = [_ev("user", "x", "해킹 시도", f"2026-06-1{i}T01:00:00.000Z") for i in range(1, 5)]
    st2 = keyword_stats(spread)
    hk2 = {k["term"]: k for k in st2["keywords"]}["해킹"]
    assert hk2["pattern"] == "지속형"


def test_stopword_and_short_filtered():
    evs = [_ev("user", "x", "그 the 이 a 비밀번호", "2026-06-11T01:00:00.000Z")]
    terms = {k["term"] for k in keyword_stats(evs)["keywords"]}
    assert "the" not in terms and "그" not in terms and "a" not in terms
    assert "비밀번호" in terms


def test_keyword_stats_mixed_ts_fixture(mixed_ts_events):
    # 공용 mixed-ts 픽스처 → keyword_stats crash 없음 + epoch-ms 이벤트 by_day가 ISO 키.
    kws = {k["term"]: k for k in keyword_stats(mixed_ts_events)["keywords"]}
    assert "비밀번호" in kws
    assert "2026-02-08" in kws["비밀번호"]["by_day"]   # epoch-ms int ts → ISO 일자 키


def test_epoch_ms_ts_no_crash():
    # history발 epoch-ms int ts 섞임 → norm_ts 통일, (e.ts or "")[:10] 슬라이스 TypeError 안 남.
    evs = [_ev("user", "x", "비밀번호 점검", 1770555950996)]
    st = keyword_stats(evs)
    assert any(k["term"] == "비밀번호" for k in st["keywords"])


def test_mask_span_not_tokenized():
    # ‹secret›·‹pii› 마스크 마커 스팬 통째 제거 → 내부 단어가 키워드로 새지 않음(secret 강조 금지).
    evs = [_ev("user", ".env", "API_KEY=‹secret› 그리고 ‹pii› 포함", "2026-06-11T01:00:00.000Z")]
    terms = {k["term"] for k in keyword_stats(evs)["keywords"]}
    assert "secret" not in terms and "pii" not in terms


def test_deterministic_tiebreak_order():
    # 동일 count(각 1회) 키워드들 → term 사전순 tie-break으로 결정적. set 순회 비결정성 무관.
    evs = [_ev("user", "x", "delta charlie bravo alpha", "2026-06-11T01:00:00.000Z")]
    terms = [k["term"] for k in keyword_stats(evs)["keywords"]]
    assert terms == ["alpha", "bravo", "charlie", "delta"]   # 전부 count 1 → 사전순


def test_by_day_distribution():
    # 엔진이 일자별 분포 제공(UI 팝업 단일진실). 이벤트당 1회 dedup → 같은날 2이벤트 = 2.
    evs = [
        _ev("user", "x", "비밀번호 점검", "2026-06-11T01:00:00.000Z"),
        _ev("user", "x", "비밀번호 재확인", "2026-06-11T05:00:00.000Z"),
        _ev("agent", "x", "비밀번호 또", "2026-06-13T01:00:00.000Z"),
    ]
    bd = {k["term"]: k for k in keyword_stats(evs)["keywords"]}["비밀번호"]["by_day"]
    assert bd == {"2026-06-11": 2, "2026-06-13": 1}


def test_token_boundary_no_substring_match():
    # "api"는 토큰 경계 — "capistrano"엔 안 잡힘(substring 재매칭 아님). JS 팝업 오매칭 원인 차단.
    evs = [_ev("user", "x", "capistrano 배포", "2026-06-11T01:00:00.000Z")]
    terms = {k["term"] for k in keyword_stats(evs)["keywords"]}
    assert "capistrano" in terms and "api" not in terms


def test_particle_strip_investigative_match():
    # "비밀번호를" → 조사 분리 → term "비밀번호"(investigative). 조사 붙은 term은 없어야.
    evs = [_ev("user", "x", "비밀번호를 확인했다", "2026-06-11T01:00:00.000Z")]
    kws = {k["term"]: k for k in keyword_stats(evs)["keywords"]}
    assert "비밀번호" in kws and kws["비밀번호"]["investigative"] is True
    assert "비밀번호를" not in kws


def test_particle_strip_token():
    evs = [_ev("user", "x", "토큰을 유출", "2026-06-11T01:00:00.000Z")]
    kws = {k["term"]: k for k in keyword_stats(evs)["keywords"]}
    assert "토큰" in kws and kws["토큰"]["investigative"] is True


def test_particle_merge_same_term():
    # "비밀번호" + "비밀번호를" → 같은 term으로 count 병합(2).
    evs = [
        _ev("user", "x", "비밀번호 점검", "2026-06-11T01:00:00.000Z"),
        _ev("agent", "x", "비밀번호를 또 봄", "2026-06-12T01:00:00.000Z"),
    ]
    kws = {k["term"]: k for k in keyword_stats(evs)["keywords"]}
    assert kws["비밀번호"]["count"] == 2


def test_no_over_strip_short_stem():
    # "회의" — 어간 "회"(1자)라 조사 "의" 분리 안 함(과분리 방지). term "회의" 유지.
    evs = [_ev("user", "x", "회의 일정 잡자", "2026-06-11T01:00:00.000Z")]
    terms = {k["term"] for k in keyword_stats(evs)["keywords"]}
    assert "회의" in terms and "회" not in terms
