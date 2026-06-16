def timeline(events):
    """ts 오름차순. ts 없는 것(None)은 빈 문자열로 취급 → 맨 앞."""
    return sorted(events, key=lambda e: (e.ts or ""))
