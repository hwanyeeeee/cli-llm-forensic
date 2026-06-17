from collections import Counter

from clfx.analyze.secrets import scan, mask


def _bypass_sessions(src):
    """permission-mode 레코드에서 bypassPermissions 세션 id 수집."""
    out = set()
    for rec in src.transcript_records():
        o = rec.obj
        if isinstance(o, dict) and o.get("type") == "permission-mode" \
                and o.get("permissionMode") == "bypassPermissions":
            sid = o.get("sessionId", "")
            if sid:                       # 빈 sessionId는 매칭 키로 부적합 → 제외(거짓 매칭 방지)
                out.add(sid)
    return out


def enrich(events, src, bypass=None):
    """tag-only enrich 패스. actor는 절대 변경 안 함(parser가 확정).
    (1) secrets.scan(preview) → email=pii / 그 외=secret 태그 + preview 마스킹.
    (2) bypassPermissions 세션(sessionId 매칭)의 read Event에 bypass-mode 태그.
    bypass=None이면 _bypass_sessions(src) 재읽기(CLI/하위호환). set 주어지면 그걸 사용(2차 재읽기 X).
    sidechain/agent-name 미사용(범위 밖, 의도적)."""
    if bypass is None:
        bypass = _bypass_sessions(src)
    for e in events:
        findings = scan(e.preview)
        kinds = {f.kind for f in findings}
        if kinds - {"email"}:
            if "secret" not in e.tags:
                e.tags.append("secret")
        if "email" in kinds:
            if "pii" not in e.tags:
                e.tags.append("pii")
        if findings:
            e.preview = mask(e.preview, findings)
        if e.action == "read" and e.session and e.session in bypass and "bypass-mode" not in e.tags:
            e.tags.append("bypass-mode")
    return events


def attribution_summary(events):
    return dict(Counter(e.actor for e in events))
