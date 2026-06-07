#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses, make_msgid, parseaddr
from pathlib import Path


ARCHIVE_DIR = Path("/srv/mailin/archive/belegeMBDS")
ATTACHMENT_DIR = Path("/srv/mbds-belege")
AUTOREPLY_FROM = "belegeMBDS@m00h.eu"
AUTOREPLY_REPLY_TO = "kasse@meschederbuendnis.de"


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "attachment.bin"


def unique_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def save_raw_message(message_bytes: bytes, prefix: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = ARCHIVE_DIR / f"{prefix}.eml"
    raw_path.write_bytes(message_bytes)
    return raw_path


def save_attachments(message, prefix: str) -> list[Path]:
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    counter = 0
    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        counter += 1
        safe_name = sanitize_filename(filename)
        output_path = ATTACHMENT_DIR / f"{prefix}-{counter:02d}-{safe_name}"
        output_path.write_bytes(payload)
        saved.append(output_path)
    return saved


def autoresponder_target(message) -> str | None:
    if message.get("Auto-Submitted") and message.get("Auto-Submitted", "").lower() != "no":
        return None
    if message.get("Precedence", "").lower() in {"bulk", "junk", "list"}:
        return None

    for header in ("Reply-To", "From"):
        addresses = getaddresses(message.get_all(header, []))
        for _, address in addresses:
            candidate = address.strip()
            if not candidate:
                continue
            lower = candidate.lower()
            if lower in {AUTOREPLY_FROM.lower(), AUTOREPLY_REPLY_TO.lower()}:
                continue
            if lower.startswith("mailer-daemon@") or lower.startswith("postmaster@"):
                continue
            return candidate
    return None


def send_autoresponse(message, received_at: datetime) -> str | None:
    recipient = autoresponder_target(message)
    if not recipient:
        return None

    date_text = received_at.strftime("%d.%m.%Y")
    time_text = received_at.strftime("%H:%M")

    response = EmailMessage()
    response["From"] = f"NoReply <{AUTOREPLY_FROM}>"
    response["To"] = recipient
    response["Reply-To"] = AUTOREPLY_REPLY_TO
    response["Subject"] = f"[NoReply] deine eMail mit Beleg vom {date_text}"
    response["Date"] = format_datetime(received_at)
    response["Message-ID"] = make_msgid(domain="m00h.eu")
    response["Auto-Submitted"] = "auto-replied"
    response["X-Auto-Response-Suppress"] = "All"
    original_message_id = message.get("Message-ID")
    if original_message_id:
        response["In-Reply-To"] = original_message_id
        response["References"] = original_message_id

    response.set_content(
        "\n".join(
            [
                "Bestaetigung des Empfangs des Belegs fuer das Mescheder Buendnis fuer Demokratie und Solidaritaet.",
                "",
                f"Dein eMail-Beleg wurde am {date_text} um {time_text} Uhr empfangen und abgespeichert.",
                "",
                "Vielen Dank und viele Gruesse",
                "Christian Heidingsfelder",
                "Kassierer Mescheder Buendnis",
                "",
                "Bitte antworte auf diese eMail an kasse@meschederbuendnis.de.",
            ]
        )
    )

    subprocess.run(
        ["/usr/sbin/sendmail", "-i", "-f", AUTOREPLY_FROM, recipient],
        input=response.as_bytes(),
        check=True,
    )
    return recipient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True)
    args = parser.parse_args()

    message_bytes = sys.stdin.buffer.read()
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    received_at = datetime.now().astimezone()
    prefix = unique_prefix()
    raw_path = save_raw_message(message_bytes, prefix)
    attachments = save_attachments(message, prefix)

    autoresponse_sent_to = None
    autoresponse_error = None
    try:
        autoresponse_sent_to = send_autoresponse(message, received_at)
    except subprocess.CalledProcessError as exc:
        autoresponse_error = f"sendmail failed rc={exc.returncode}"

    fragments = [
        f"mail-router recipient={args.recipient}",
        f"raw={raw_path}",
        f"attachments={len(attachments)}",
    ]
    if autoresponse_sent_to:
        fragments.append(f"autoresponse_to={autoresponse_sent_to}")
    if autoresponse_error:
        fragments.append(f"autoresponse_error={autoresponse_error}")

    print(" ".join(fragments), file=sys.stdout, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
