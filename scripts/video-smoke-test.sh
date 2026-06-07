#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${TARGET_HOST:-m00h}"
MODEL="${MODEL:-tiny}"

usage() {
  cat <<'USAGE'
Usage: scripts/video-smoke-test.sh [--host <host>] [--model <tiny|small|...>]

Create a tiny synthetic video on the target host and run it through the deployed
Faketest video extraction path. This validates ffprobe, ffmpeg, the worker
import, the transcription wrapper and graceful no-speech handling.

The generated video contains a tone, not human speech; a missing transcript is
therefore acceptable as long as the worker returns metadata and no Python crash.
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
    --model)
      MODEL="${2-}"
      shift 2
      ;;
    --model=*)
      MODEL="${1#*=}"
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

ssh "$TARGET_HOST" "FAKETEST_SMOKE_MODEL=$(printf '%q' "$MODEL") bash -s" <<'REMOTE'
set -euo pipefail
work="$(mktemp -d /tmp/faketest-video-smoke.XXXXXX)"
mkdir -p "$work/job/extracted"
ffmpeg -y -f lavfi -i color=c=black:s=320x180:d=2 -f lavfi -i sine=frequency=440:duration=2 -shortest -c:v libx264 -c:a aac "$work/test.mp4" >"$work/create.log" 2>&1
FAKETEST_SMOKE_WORK="$work" /opt/faketest-transcribe/venv/bin/python - <<'PY'
import importlib.util, json, os
from pathlib import Path
work = Path(os.environ['FAKETEST_SMOKE_WORK'])
model = os.environ.get('FAKETEST_SMOKE_MODEL', 'tiny')
spec=importlib.util.spec_from_file_location('fw', '/usr/local/sbin/faketest-worker.py')
fw=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)
settings=json.load(open('/etc/faketest/settings.json'))
settings.setdefault('video', {})['transcribe_command'] = '/opt/faketest-transcribe/venv/bin/python /usr/local/sbin/faketest-transcribe.py --language de --model %s --timeout 180 {audio}' % model
text, err=fw.extract_video(work / 'job', work / 'test.mp4', settings)
print('work=%s' % work)
print('text_len=%d' % len(text))
print('has_metadata=%s' % ('Videometadaten' in text))
print('has_transcript=%s' % ('Automatisches Transkript' in text))
print('err=%s' % err)
if 'Videometadaten' not in text:
    raise SystemExit(1)
PY
REMOTE
