#!/usr/bin/env bash
# Usage: verify-android.sh <apk-path> [package-id]
#
# 연결된 emulator/device에 APK 설치 → 런처 인텐트로 기동 → 스크린캡처 → logcat
# 마지막 30줄에서 fatal/AndroidRuntime 검사. 크래시 없으면 exit 0.
#
# 호출 방식: plan.md의 acceptance: 라인에 사용자가 명시할 때만 panel 0이 실행.
# 훅 아님, 자동 아님. 디바이스/에뮬레이터는 호출 전에 사용자가 켜둬야 함.
set -euo pipefail
APK="${1:?apk path required}"
PKG="${2:-}"

adb install -r -t "$APK" >/dev/null

if [ -z "$PKG" ]; then
  PKG=$(aapt dump badging "$APK" 2>/dev/null | sed -n "s/^package: name='\([^']*\)'.*/\1/p")
fi
[ -z "$PKG" ] && { echo "package id 미감지 (인자 또는 aapt 필요)" >&2; exit 2; }

adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null
sleep 3

mkdir -p .harness/artifacts
adb exec-out screencap -p > ".harness/artifacts/android-$(date +%H%M%S).png"

LOG=$(adb logcat -d -t 30 2>/dev/null | grep -iE 'fatal|androidruntime' || true)
if [ -n "$LOG" ]; then
  echo "crash detected:" >&2
  printf '%s\n' "$LOG" >&2
  exit 1
fi

echo "android verify pass"
