#!/usr/bin/env bash
# Usage: verify-ios.sh <app-bundle-path> [bundle-id] [simulator-udid]
#
# Simulator 부팅 → 앱 설치/기동 → 스크린샷 → log에 'crashed' 검사. 크래시 없으면 exit 0.
#
# 호출 방식: plan.md의 acceptance: 라인에 사용자가 명시할 때만 panel 0이 실행.
# 훅 아님, 자동 아님. simulator UDID 생략 시 'booted' (이미 켜진 시뮬 사용).
set -euo pipefail
APP="${1:?app path required}"
BUNDLE="${2:-}"
UDID="${3:-booted}"

if [ "$UDID" != "booted" ]; then
  xcrun simctl boot "$UDID" 2>/dev/null || true
fi

xcrun simctl install "$UDID" "$APP"

if [ -z "$BUNDLE" ]; then
  BUNDLE=$(plutil -extract CFBundleIdentifier raw "$APP/Info.plist" 2>/dev/null)
fi
[ -z "$BUNDLE" ] && { echo "bundle id 미감지 (인자 또는 Info.plist 필요)" >&2; exit 2; }

xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null
sleep 3

mkdir -p .harness/artifacts
xcrun simctl io "$UDID" screenshot ".harness/artifacts/ios-$(date +%H%M%S).png"

if xcrun simctl spawn "$UDID" log show --last 1m --predicate 'eventMessage contains "crashed"' 2>/dev/null | grep -q crashed; then
  echo "crash detected" >&2
  exit 1
fi

echo "ios verify pass"
