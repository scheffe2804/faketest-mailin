#!/usr/bin/env bash
set -euo pipefail

PREFIX="${PREFIX:-/opt/faketest-transcribe}"
PYTHON="${PYTHON:-python3}"
MODEL="${MODEL:-small}"

usage() {
  cat <<'USAGE'
Usage: scripts/install-faster-whisper.sh [options]

Install a local faster-whisper runtime into an isolated virtual environment.
This script is intended to run on the Faketest runtime host. It changes the
local system by creating/updating PREFIX, downloading Python wheels and warming
the selected model cache.

Options:
  --prefix <path>   Install prefix. Default: /opt/faketest-transcribe
  --python <cmd>    Python command. Default: python3
  --model <name>    Warm up model. Default: small
  -h, --help        Show help

Environment:
  PREFIX, PYTHON, MODEL can also be used.

After installation, use this transcribe command in settings:
  /opt/faketest-transcribe/venv/bin/python /usr/local/sbin/faketest-transcribe.py --language de --model small --timeout 900 {audio}
USAGE
}

while [[ ${1-} ]]; do
  case "$1" in
    --prefix)
      PREFIX="${2-}"
      shift 2
      ;;
    --prefix=*)
      PREFIX="${1#*=}"
      shift
      ;;
    --python)
      PYTHON="${2-}"
      shift 2
      ;;
    --python=*)
      PYTHON="${1#*=}"
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

echo "Install prefix: $PREFIX"
echo "Python: $PYTHON"
echo "Warm-up model: $MODEL"

sudo mkdir -p "$PREFIX"
sudo chown "$(id -u):$(id -g)" "$PREFIX"

"$PYTHON" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$PREFIX/venv/bin/python" -m pip install faster-whisper

"$PREFIX/venv/bin/python" - <<PY
from faster_whisper import WhisperModel
model = WhisperModel(${MODEL@Q}, device='cpu', compute_type='int8', cpu_threads=2)
print('loaded faster-whisper model:', ${MODEL@Q})
PY

cat <<EOF

faster-whisper installed.

Recommended settings command:
  $PREFIX/venv/bin/python /usr/local/sbin/faketest-transcribe.py --language de --model $MODEL --timeout 900 {audio}
EOF
