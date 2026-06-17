from clfx.event import ts_key


def timeline(events):
    """ts 오름차순(연대순). ts 없는 것(None)은 맨 앞.
    혼재 타입(int epoch-ms / str ISO)·동일초(ISO 밀리초無 vs epoch 밀리초有) 모두 방어 —
    ts_key가 datetime으로 파싱해 실제 시각 비교(사전순 아님 → "."<"Z" 류 결함 차단).
    파서가 수집 시 norm_ts로 표시값을 정규화하지만 직접 호출도 동일 보장."""
    return sorted(events, key=lambda e: ts_key(e.ts))
