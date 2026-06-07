#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${TARGET_HOST:-m00h}"

usage() {
  cat <<'USAGE'
Usage: scripts/check-video-runtime.sh [--host <host>]

Check whether the Faketest video runtime is ready on the target host.
This is read-only.
USAGE
}

while [[ ${1-} ]]; do
  case "$1" in
    --host)
      TARGET_HOST="${2-}"
      shift 2
      ;;
    --host=*)
      TARGET_HOST="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ssh "$TARGET_HOST" 'set -euo pipefail
echo "== binaries =="
for cmd in ffmpeg ffprobe /opt/faketest-transcribe/venv/bin/python /opt/faketest-transcribe/venv/bin/yt-dlp /usr/local/sbin/faketest-transcribe.py /usr/local/sbin/faketest-worker.py; do
  if [[ -x "$cmd" || -n "$(command -v "$cmd" 2>/dev/null || true)" ]]; then
    echo "OK $cmd"
  else
    echo "MISSING $cmd"
  fi
done

echo "== versions =="
ffmpeg -version | sed -n "1p"
ffprobe -version | sed -n "1p"
/opt/faketest-transcribe/venv/bin/python --version
/opt/faketest-transcribe/venv/bin/yt-dlp --version

echo "== python backend =="
/opt/faketest-transcribe/venv/bin/python - <<"PY"
from faster_whisper import WhisperModel
print("faster_whisper import ok")
PY

echo "== settings =="
sudo python3 - <<"PY"
import json
s=json.load(open("/etc/faketest/settings.json"))
v=s.get("video", {})
for key in ["enabled", "transcribe_command", "yt_dlp_enabled", "yt_dlp_command", "yt_dlp_allowed_hosts", "max_duration_seconds", "max_download_bytes"]:
    print("%s=%r" % (key, v.get(key)))
PY

echo "== systemd =="
systemctl is-enabled faketest-worker.timer
systemctl is-active faketest-worker.timer
'
