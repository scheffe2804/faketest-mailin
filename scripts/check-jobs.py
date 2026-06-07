#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_BASE = Path("/srv/tailshare/Faketest-Mails/Eingang")


def is_backup_path(path: Path) -> bool:
    return any("backup" in part.lower() for part in path.parts)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def summarize(meta_path: Path) -> dict[str, Any] | None:
    meta = read_json(meta_path)
    if not meta:
        return None
    job_dir = meta_path.parent
    request_path = job_dir / "publish_request.json"
    request = read_json(request_path) if request_path.exists() else None
    return {
        "path": str(job_dir),
        "job_id": meta.get("job_id"),
        "status": meta.get("status"),
        "publish_status": meta.get("publish_status"),
        "has_publish_request": request_path.exists(),
        "publish_request_status": request.get("status") if request else None,
        "subject": meta.get("subject"),
        "staging_url": meta.get("staging_url"),
        "live_url": meta.get("live_url"),
        "blocked_reason": meta.get("live_blocked_reason"),
        "notes_last": (meta.get("notes") or [])[-3:],
    }


def interesting(row: dict[str, Any], mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "publish":
        return bool(row.get("has_publish_request")) and row.get("publish_status") != "live_published"
    if mode == "failed":
        return row.get("status") in {"fehler", "limit_erreicht", "freigabe_abgelaufen"}
    if mode == "pending":
        return row.get("status") not in {"erledigt", "fehler", "limit_erreicht", "freigabe_abgelaufen"}
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="List Faketest jobs without counting backup snapshots as active jobs.")
    parser.add_argument("--base", default=str(DEFAULT_BASE), help="Base Eingang directory")
    parser.add_argument("--mode", choices=["publish", "failed", "pending", "all"], default="publish")
    parser.add_argument("--include-backups", action="store_true", help="Include backup subdirectories")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    base = Path(args.base)
    rows: list[dict[str, Any]] = []
    for meta_path in sorted(base.rglob("meta.json")) if base.exists() else []:
        if not args.include_backups and is_backup_path(meta_path):
            continue
        row = summarize(meta_path)
        if row and interesting(row, args.mode):
            rows.append(row)

    if args.format == "json":
        print(json.dumps({"count": len(rows), "jobs": rows}, ensure_ascii=False, indent=2))
    else:
        print("count=%d mode=%s" % (len(rows), args.mode))
        for row in rows:
            print("---")
            for key in ["job_id", "status", "publish_status", "publish_request_status", "subject", "staging_url", "live_url", "blocked_reason", "path"]:
                print("%s=%s" % (key, row.get(key)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
