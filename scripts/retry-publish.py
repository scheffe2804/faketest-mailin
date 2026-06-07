#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_BASE = Path("/srv/tailshare/Faketest-Mails/Eingang")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_job(base: Path, job_id: str) -> Path:
    matches = []
    for meta_path in base.rglob("meta.json") if base.exists() else []:
        if any("backup" in part.lower() for part in meta_path.parts):
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("job_id") == job_id:
            matches.append(meta_path.parent)
    if not matches:
        raise SystemExit("Job not found: %s" % job_id)
    if len(matches) > 1:
        raise SystemExit("Multiple current jobs found for %s: %s" % (job_id, ", ".join(str(x) for x in matches)))
    return matches[0]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark one approved Faketest publication request for retry.")
    parser.add_argument("job_id")
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--reason", required=True, help="Human-readable retry reason")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    job = find_job(Path(args.base), args.job_id)
    meta_path = job / "meta.json"
    request_path = job / "publish_request.json"
    if not request_path.exists():
        raise SystemExit("No publish_request.json for job: %s" % job)

    meta = load(meta_path)
    request = load(request_path)
    stamp = now_iso()

    meta["publish_status"] = "retry"
    meta.setdefault("notes", []).append({"at": stamp, "note": "Retry requested: " + args.reason})
    request["status"] = "retry"
    request["retry_requested_at"] = stamp
    request["retry_reason"] = args.reason

    lock = job / "worker.lock"

    if args.dry_run:
        print("job=%s" % job)
        print("would set meta.publish_status=retry")
        print("would set publish_request.status=retry")
        print("would remove lock=%s exists=%s" % (lock, lock.exists()))
        return 0

    save(meta_path, meta)
    save(request_path, request)
    if lock.exists():
        os.unlink(lock)
    print("retry prepared job=%s at=%s" % (args.job_id, stamp))
    print("Start the worker, for example: sudo systemctl start faketest-worker.service")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
