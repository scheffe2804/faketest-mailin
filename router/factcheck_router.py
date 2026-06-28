#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from pathlib import Path


SETTINGS_PATH = Path("/etc/faketest/settings.json")


def load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def sanitize_component(value: str, fallback: str = "unbekannt") -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9._@+-]+", "_", value)
    value = value.replace("@", "_at_")
    value = re.sub(r"_+", "_", value).strip("._-")
    return value[:80] or fallback


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" ._")
    return cleaned[:180] or "attachment.bin"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(1, 1000):
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not create unique path for {path}")


def extract_bodies(message) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        if (part.get_content_disposition() or "").lower() == "attachment":
            continue
        content_type = part.get_content_type().lower()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = str(part.get_content())
        except Exception:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")
        if content_type == "text/plain":
            text_parts.append(content)
        else:
            html_parts.append(content)
    return "\n\n".join(text_parts).strip(), "\n\n".join(html_parts).strip()


def should_ignore_reply(message) -> bool:
    auto_submitted = message.get("Auto-Submitted", "").lower().strip()
    if auto_submitted and auto_submitted != "no":
        return True
    if message.get("Precedence", "").lower().strip() in {"bulk", "junk", "list"}:
        return True
    if message.get("List-Id"):
        return True
    return False


def detect_approval(text: str, subject: str) -> str | None:
    haystack = f"{subject}\n{text}"
    match = re.search(r"\bFREIGABE\s+([0-9]{8}T[0-9]{6}Z-[a-f0-9]{8})\b", haystack, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b([0-9]{8}T[0-9]{6}Z-[a-f0-9]{8})\b", subject, flags=re.IGNORECASE)
    if match and "freigabe" in haystack.lower():
        return match.group(1)
    return None


def detect_publish_request(subject: str) -> tuple[str, str] | None:
    match = re.search(
        r"\[\s*FT-PUB\s+([0-9]{8}T[0-9]{6}Z-[a-f0-9]{8})\s+([A-Z0-9][A-Z0-9-]{8,80})\s*\]",
        subject or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2).upper()


def detect_video_continue_request(subject: str) -> tuple[str, str, str] | None:
    match = re.search(
        r"\[\s*FT-VID\s+([0-9]{8}T[0-9]{6}Z-[a-f0-9]{8})\s+(NEXT|SYNTHESIS)\s+([A-Z0-9][A-Z0-9-]{8,80})\s*\]",
        subject or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2).upper(), match.group(3).upper()


def find_job_dir(base_dir: Path, job_id: str) -> Path | None:
    for root in [base_dir / "Eingang", base_dir / "Fehler", base_dir / "Erledigt"]:
        if not root.exists():
            continue
        for candidate in root.rglob(f"{job_id}*"):
            if candidate.is_dir():
                return candidate
    return None


def write_approval(base_dir: Path, job_id: str, sender: str, message_bytes: bytes) -> bool:
    job_dir = find_job_dir(base_dir, job_id)
    if not job_dir:
        return False
    approval = {
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approved_by": sender,
        "job_id": job_id,
    }
    (job_dir / "approval.json").write_text(json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (job_dir / "approval.eml").write_bytes(message_bytes)
    (job_dir / "status.txt").write_text("STATUS: freigegeben\n", encoding="utf-8")
    try:
        meta_path = job_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "freigegeben"
        meta["approval"] = approval
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    return True


def write_publish_request(base_dir: Path, job_id: str, token: str, sender: str, subject: str, message_bytes: bytes, settings: dict) -> bool:
    job_dir = find_job_dir(base_dir, job_id)
    if not job_dir:
        return False
    publish_cfg = settings.get("publish", {})
    allowed_sender = str(publish_cfg.get("allowed_sender", "chrisheidingsfelder@gmail.com")).strip().lower()
    request = {
        "requested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_by": sender,
        "allowed_sender": allowed_sender,
        "job_id": job_id,
        "token": token,
        "subject": subject,
        "status": "pending" if sender == allowed_sender else "rejected_invalid_sender",
    }
    publish_dir = job_dir / "publish"
    publish_dir.mkdir(exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (publish_dir / f"request-{suffix}.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (publish_dir / f"request-{suffix}.eml").write_bytes(message_bytes)
    (job_dir / "publish_request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        meta_path = job_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("publish_requests", []).append(request)
        if sender != allowed_sender:
            meta["publish_status"] = "rejected_invalid_sender"
        else:
            meta["publish_status"] = "live_requested"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    return True


def write_video_continue_request(base_dir: Path, job_id: str, action: str, token: str, sender: str, subject: str, message_bytes: bytes, settings: dict) -> bool:
    job_dir = find_job_dir(base_dir, job_id)
    if not job_dir:
        return False
    publish_cfg = settings.get("publish", {})
    allowed_sender = str(publish_cfg.get("allowed_sender", "chrisheidingsfelder@gmail.com")).strip().lower()
    request = {
        "requested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_by": sender,
        "allowed_sender": allowed_sender,
        "job_id": job_id,
        "action": action,
        "token": token,
        "subject": subject,
        "status": "pending" if sender == allowed_sender else "rejected_invalid_sender",
    }
    video_dir = job_dir / "video"
    video_dir.mkdir(exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (video_dir / f"continue-{suffix}.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (video_dir / f"continue-{suffix}.eml").write_bytes(message_bytes)
    (job_dir / "video_continue_request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        meta_path = job_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("video_continue_requests", []).append(request)
        if sender == allowed_sender:
            meta["status"] = "wartet_auf_bearbeitung"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if sender == allowed_sender:
            (job_dir / "status.txt").write_text("STATUS: wartet_auf_bearbeitung\n", encoding="utf-8")
    except Exception:
        pass
    return True


def make_job_dir(base_dir: Path, sender: str, received_at: datetime, job_id: str) -> Path:
    sender_part = sanitize_component(sender)
    folder_name = f"{job_id}_{sender_part}"
    folder = base_dir / "Eingang" / received_at.strftime("%Y") / received_at.strftime("%m") / folder_name
    folder.mkdir(parents=True, exist_ok=False)
    for name in ["attachments", "extracted", "research", "result"]:
        (folder / name).mkdir()
    return folder


def save_attachments(message, attachments_dir: Path, settings: dict) -> tuple[list[dict], list[str]]:
    attachments: list[dict] = []
    hard_errors: list[str] = []
    limits = settings["limits"]
    blocked_ext = {x.lower() for x in settings.get("blocked_extensions", [])}
    allowed_ext = {x.lower() for x in settings.get("allowed_extensions", [])}
    counter = 0
    for part in message.walk():
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").lower()
        if not filename and disposition != "attachment":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        counter += 1
        original = filename or f"attachment-{counter}.bin"
        safe_name = sanitize_filename(original)
        suffix = Path(safe_name).suffix.lower()
        blocked = False
        reasons: list[str] = []
        if counter > int(limits["attachments_per_mail"]):
            blocked = True
            reasons.append("zu viele Anhaenge")
        if len(payload) > int(limits["attachment_bytes"]):
            blocked = True
            reasons.append("Anhang zu gross")
        if suffix in blocked_ext:
            blocked = True
            reasons.append("gefaehrlicher Dateityp")
        if suffix and suffix not in allowed_ext:
            blocked = True
            reasons.append("nicht erlaubter Dateityp")
        output_path = unique_path(attachments_dir / safe_name)
        output_path.write_bytes(payload)
        info = {
            "original_name": original,
            "saved_name": output_path.name,
            "path": str(output_path),
            "size": len(payload),
            "content_type": part.get_content_type(),
            "extension": suffix,
            "blocked": blocked,
            "block_reasons": reasons,
        }
        attachments.append(info)
        if blocked:
            hard_errors.extend([f"{safe_name}: {reason}" for reason in reasons])
    return attachments, hard_errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--original-recipient", default="")
    parser.add_argument("--sender", default="")
    args = parser.parse_args()

    settings = load_settings()
    base_dir = Path(settings["base_dir"])
    base_dir.mkdir(parents=True, exist_ok=True)
    for name in ["Eingang", "Erledigt", "Fehler", "Logs", "state"]:
        (base_dir / name).mkdir(exist_ok=True)

    message_bytes = sys.stdin.buffer.read()
    received_at = datetime.now(timezone.utc)
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    from_name, from_addr = parseaddr(message.get("From", ""))
    sender = (args.sender or from_addr or "unknown").strip().lower()
    subject = str(message.get("Subject", ""))
    body_text, body_html = extract_bodies(message)

    publish_request = detect_publish_request(subject)
    if publish_request:
        publish_job, publish_token = publish_request
        ok = write_publish_request(base_dir, publish_job, publish_token, sender, subject, message_bytes, settings)
        print(f"factcheck-router publish job={publish_job} sender={sender} ok={ok}", flush=True)
        return 0

    video_continue = detect_video_continue_request(subject)
    if video_continue:
        video_job, video_action, video_token = video_continue
        ok = write_video_continue_request(base_dir, video_job, video_action, video_token, sender, subject, message_bytes, settings)
        print(f"factcheck-router video job={video_job} action={video_action} sender={sender} ok={ok}", flush=True)
        return 0

    approval_job = detect_approval(body_text or body_html, subject)
    if approval_job:
        ok = write_approval(base_dir, approval_job, sender, message_bytes)
        print(f"factcheck-router approval job={approval_job} sender={sender} ok={ok}", flush=True)
        return 0

    job_id = received_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    job_dir = make_job_dir(base_dir, sender, received_at, job_id)
    (job_dir / "mail.eml").write_bytes(message_bytes)
    (job_dir / "body.txt").write_text(body_text + ("\n" if body_text else ""), encoding="utf-8")
    if body_html:
        (job_dir / "body.html").write_text(body_html + "\n", encoding="utf-8")

    hard_errors: list[str] = []
    if len(message_bytes) > int(settings["limits"]["message_bytes"]):
        hard_errors.append("Mailgroesse ueber Limit")
    if should_ignore_reply(message):
        hard_errors.append("Auto-/Listenmail wird nicht beantwortet")

    attachments, attachment_errors = save_attachments(message, job_dir / "attachments", settings)
    hard_errors.extend(attachment_errors)

    reply_candidates = getaddresses(message.get_all("Reply-To", []) or message.get_all("From", []))
    reply_to = next((addr.strip().lower() for _, addr in reply_candidates if addr), from_addr or sender)
    status = "abgelehnt_harte_grenze" if hard_errors else "wartet_auf_bearbeitung"

    metadata = {
        "job_id": job_id,
        "received_at": received_at.isoformat(timespec="seconds"),
        "recipient": args.original_recipient or args.recipient,
        "router_recipient": args.recipient,
        "envelope_sender": args.sender,
        "from": {"name": from_name, "address": from_addr},
        "sender": sender,
        "reply_to": reply_to,
        "subject": subject,
        "message_id": message.get("Message-ID"),
        "attachments": attachments,
        "hard_errors": hard_errors,
        "status": status,
    }
    (job_dir / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (job_dir / "job.json").write_text(json.dumps({"job_id": job_id, "status": status}, indent=2) + "\n", encoding="utf-8")
    (job_dir / "status.txt").write_text(f"STATUS: {status}\n", encoding="utf-8")
    (job_dir / "auftrag.md").write_text(
        "\n".join([
            f"# Faketest-Auftrag {job_id}",
            "",
            f"- Eingang: {received_at.isoformat(timespec='seconds')}",
            f"- Von: {sender}",
            f"- Antwort an: {reply_to}",
            f"- Betreff: {subject or '(ohne Betreff)'}",
            f"- Status: {status}",
            "",
            "## Harte Fehler",
            *(f"- {item}" for item in hard_errors),
            *( ["- keine"] if not hard_errors else [] ),
            "",
            "## Mailtext",
            body_text or "(kein Textinhalt erkannt)",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"factcheck-router job={job_id} sender={sender} dir={job_dir} status={status} attachments={len(attachments)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
