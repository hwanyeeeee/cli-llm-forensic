def timeline(events):
    """ts 오름차순. ts 없는 것(None)은 맨 앞.
    혼재 타입(int epoch-ms / str ISO) 안전 — str 비교로 TypeError 방지(파서가 정규화하지만 직접 호출도 방어)."""
    return sorted(events, key=lambda e: "" if e.ts is None else str(e.ts))
