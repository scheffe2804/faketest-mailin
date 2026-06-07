#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


SETTINGS_PATH = Path("/etc/faketest/settings.json")


def load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def cleanup_jobs(settings: dict) -> list[str]:
    base = Path(settings["base_dir"])
    retention = settings["retention_days"]
    now = datetime.now(timezone.utc)
    removed: list[str] = []
    for meta_path in (base.rglob("meta.json") if base.exists() else []):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = meta.get("status")
        if status in {"in_bearbeitung", "wartet_auf_freigabe", "freigegeben", "wartet_auf_bearbeitung"}:
            continue
        received = parse_dt(meta.get("received_at", ""))
        if not received:
            continue
        if status == "erledigt":
            days = int(retention.get("completed", 90))
        elif status == "freigabe_abgelaufen":
            days = int(retention.get("expired_approval", 30))
        else:
            days = int(retention.get("failed", 30))
        if now - received > timedelta(days=days):
            shutil.rmtree(meta_path.parent, ignore_errors=True)
            removed.append(str(meta_path.parent))
    return removed


def cleanup_rate_state(settings: dict) -> None:
    db = Path(settings["base_dir"]) / "state" / "faketest.sqlite"
    if not db.exists():
        return
    cutoff = int(time.time()) - int(settings["retention_days"].get("rate_state", 14)) * 86400
    conn = sqlite3.connect(db)
    try:
        conn.execute("delete from events where ts < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    settings = load_settings()
    removed = cleanup_jobs(settings)
    cleanup_rate_state(settings)
    log_dir = Path(settings["base_dir"]) / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "cleanup.log").open("a", encoding="utf-8").write("%s removed=%d\n" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), len(removed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
