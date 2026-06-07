#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TARGET_HOST="${TARGET_HOST:-m00h}"
WORKER_SRC="$REPO_ROOT/host-tools/faketest-worker.py"
CLEANUP_SRC="$REPO_ROOT/host-tools/faketest-cleanup.py"
TRANSCRIBE_SRC="$REPO_ROOT/host-tools/faketest-transcribe.py"
SETTINGS_SRC="$REPO_ROOT/config/faketest/settings.json"

DEPLOY_SETTINGS=0
DEPLOY_UNITS=0

usage() {
  cat <<'USAGE'
Usage: scripts/deploy-worker.sh [options]

Deploy Faketest worker scripts to the runtime host with syntax checks and
systemd verification. By default this does not deploy real settings or units.

Options:
  --host <host>        Target host. Default: env TARGET_HOST or m00h
  --settings          Also deploy config/faketest/settings.json
  --units             Also deploy systemd service/timer units
  -h, --help          Show help

Examples:
  scripts/deploy-worker.sh
  scripts/deploy-worker.sh --settings --units
USAGE
}

while [[ ${1-} ]]; do
  case "$1" in
    --host)
      TARGET_HOST="${2-}"
      [[ -n "$TARGET_HOST" ]] || { echo "Missing --host value" >&2; exit 2; }
      shift 2
      ;;
    --host=*)
      TARGET_HOST="${1#*=}"
      shift
      ;;
    --settings)
      DEPLOY_SETTINGS=1
      shift
      ;;
    --units)
      DEPLOY_UNITS=1
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

[[ -f "$WORKER_SRC" ]] || { echo "Missing worker: $WORKER_SRC" >&2; exit 1; }
[[ -f "$CLEANUP_SRC" ]] || { echo "Missing cleanup: $CLEANUP_SRC" >&2; exit 1; }
[[ -f "$TRANSCRIBE_SRC" ]] || { echo "Missing transcribe wrapper: $TRANSCRIBE_SRC" >&2; exit 1; }

echo "== Local syntax checks =="
python3 -m py_compile "$WORKER_SRC" "$CLEANUP_SRC" "$TRANSCRIBE_SRC"

if [[ "$DEPLOY_SETTINGS" -eq 1 ]]; then
  [[ -f "$SETTINGS_SRC" ]] || { echo "Missing real settings: $SETTINGS_SRC" >&2; exit 1; }
  python3 -m json.tool "$SETTINGS_SRC" >/dev/null
fi

tmp_base="/tmp/faketest-deploy-$(date -u +%Y%m%dT%H%M%SZ)-$$"

echo "== Copy scripts to $TARGET_HOST =="
scp "$WORKER_SRC" "$TARGET_HOST:$tmp_base-worker.py"
scp "$CLEANUP_SRC" "$TARGET_HOST:$tmp_base-cleanup.py"
scp "$TRANSCRIBE_SRC" "$TARGET_HOST:$tmp_base-transcribe.py"

if [[ "$DEPLOY_SETTINGS" -eq 1 ]]; then
  scp "$SETTINGS_SRC" "$TARGET_HOST:$tmp_base-settings.json"
fi

if [[ "$DEPLOY_UNITS" -eq 1 ]]; then
  for unit in faketest-worker.service faketest-worker.timer faketest-cleanup.service faketest-cleanup.timer; do
    scp "$REPO_ROOT/host-tools/$unit" "$TARGET_HOST:$tmp_base-$unit"
  done
fi

echo "== Install on $TARGET_HOST =="
ssh "$TARGET_HOST" "set -euo pipefail
sudo install -m 0755 '$tmp_base-worker.py' /usr/local/sbin/faketest-worker.py
sudo install -m 0755 '$tmp_base-cleanup.py' /usr/local/sbin/faketest-cleanup.py
sudo install -m 0755 '$tmp_base-transcribe.py' /usr/local/sbin/faketest-transcribe.py
if [[ '$DEPLOY_SETTINGS' -eq 1 ]]; then
  sudo install -m 0640 -o root -g chris '$tmp_base-settings.json' /etc/faketest/settings.json
  if [[ -e /srv/mailin/config/faketest ]]; then
    sudo install -m 0640 -o root -g chris '$tmp_base-settings.json' /srv/mailin/config/faketest/settings.json
  fi
fi
if [[ '$DEPLOY_UNITS' -eq 1 ]]; then
  for unit in faketest-worker.service faketest-worker.timer faketest-cleanup.service faketest-cleanup.timer; do
    sudo install -m 0644 '$tmp_base-'\"\$unit\" /etc/systemd/system/\"\$unit\"
  done
  sudo systemctl daemon-reload
fi
python3 - <<'PY'
import py_compile, tempfile
for src in ['/usr/local/sbin/faketest-worker.py', '/usr/local/sbin/faketest-cleanup.py', '/usr/local/sbin/faketest-transcribe.py']:
    c = tempfile.NamedTemporaryFile(prefix='faketest-', suffix='.pyc', delete=False).name
    py_compile.compile(src, cfile=c, doraise=True)
    print('syntax ok', src, c)
PY
systemctl is-enabled faketest-worker.timer
systemctl is-active faketest-worker.timer
systemctl is-enabled faketest-cleanup.timer || true
systemctl is-active faketest-cleanup.timer || true
stat -c '%U %G %a %n' /etc/faketest/settings.json || true
"

echo "Deploy complete."
