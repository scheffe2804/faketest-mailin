#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
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


BASE_DIR = Path("/srv/tailshare/Ki-Mails")
AUTOREPLY_FROM = "ki@m00h.eu"
FREISCHALTUNG = "chrisheidingsfelder@gmail.com"


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
        disposition = (part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            continue
        content_type = part.get_content_type().lower()
        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")

        if content_type == "text/plain":
            text_parts.append(str(content))
        elif content_type == "text/html":
            html_parts.append(str(content))

    return "\n\n".join(text_parts).strip(), "\n\n".join(html_parts).strip()


def parse_control_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*(AKTION|THEMA|ZIEL|AUFGABE)\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if match:
            fields[match.group(1).upper()] = match.group(2).strip()
    return fields


def create_message_dir(sender: str, received_at: datetime) -> Path:
    sender_part = sanitize_component(sender)
    short_id = uuid.uuid4().hex[:8]
    name = f"{received_at.strftime('%Y-%m-%d_%H%M%S')}_{sender_part}_{short_id}"
    folder = BASE_DIR / "Eingang" / received_at.strftime("%Y") / received_at.strftime("%m") / name
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "attachments").mkdir()
    return folder


def save_attachments(message, attachments_dir: Path) -> list[dict[str, str | int]]:
    saved: list[dict[str, str | int]] = []
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
        output_path = unique_path(attachments_dir / safe_name)
        output_path.write_bytes(payload)
        saved.append(
            {
                "original_name": original,
                "saved_name": output_path.name,
                "path": str(output_path),
                "size": len(payload),
                "content_type": part.get_content_type(),
            }
        )
    return saved


def write_topic_index(message_dir: Path, fields: dict[str, str], subject: str, received_at: datetime) -> str | None:
    topic = fields.get("THEMA", "").strip()
    if not topic:
        return None
    topic_name = sanitize_component(topic, fallback="thema")
    topic_dir = BASE_DIR / "Themen" / topic_name
    topic_dir.mkdir(parents=True, exist_ok=True)
    index_path = topic_dir / "index.md"
    relative = message_dir
    line = f"- {received_at.isoformat(timespec='seconds')} | {subject or '(ohne Betreff)'} | {relative}\n"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    link_path = topic_dir / message_dir.name
    try:
        if not link_path.exists():
            link_path.symlink_to(message_dir)
    except OSError:
        pass
    return str(index_path)


def should_autoreply(message) -> bool:
    auto_submitted = message.get("Auto-Submitted", "").lower().strip()
    if auto_submitted and auto_submitted != "no":
        return False
    if message.get("Precedence", "").lower() in {"bulk", "junk", "list"}:
        return False
    return True


def send_autoresponse(message, target: str, message_dir: Path, metadata: dict, attachments: list[dict[str, str | int]]) -> str | None:
    if not target or not should_autoreply(message):
        return None

    subject = metadata.get("subject") or "(ohne Betreff)"
    fields = metadata.get("control_fields") or {}
    response = EmailMessage()
    response["From"] = f"KI-Mailrouter <{AUTOREPLY_FROM}>"
    response["To"] = target
    response["Reply-To"] = FREISCHALTUNG
    response["Subject"] = f"[ki@m00h.eu] Eingang bestaetigt: {subject}"
    response["Date"] = format_datetime(datetime.now().astimezone())
    response["Message-ID"] = make_msgid(domain="m00h.eu")
    response["Auto-Submitted"] = "auto-replied"
    response["X-Auto-Response-Suppress"] = "All"
    original_message_id = message.get("Message-ID")
    if original_message_id:
        response["In-Reply-To"] = original_message_id
        response["References"] = original_message_id

    attachment_lines = [f" - {item['saved_name']} ({item['size']} Bytes)" for item in attachments]
    if not attachment_lines:
        attachment_lines = [" - keine"]

    response.set_content(
        "\n".join(
            [
                "Deine Mail an ki@m00h.eu wurde gespeichert.",
                "",
                "Ablageordner:",
                f" {message_dir}",
                "",
                "Gespeichert als:",
                " - mail.eml       Originalmail unveraendert",
                " - body.txt       Textinhalt der Mail, falls vorhanden",
                " - body.html      HTML-Inhalt, falls vorhanden",
                " - meta.json      Metadaten und erkannte Steuerfelder",
                " - auftrag.md     lesbare Zusammenfassung des Auftrags",
                " - status.txt     aktueller Bearbeitungsstatus",
                " - attachments/   gespeicherte Anhaenge",
                "",
                "Erkannte Angaben:",
                f" - AKTION: {fields.get('AKTION', 'nicht angegeben')}",
                f" - THEMA: {fields.get('THEMA', 'nicht angegeben')}",
                f" - ZIEL: {fields.get('ZIEL', 'nicht angegeben')}",
                f" - AUFGABE: {fields.get('AUFGABE', 'nicht angegeben')}",
                "",
                "Anhaenge:",
                *attachment_lines,
                "",
                f"Status: {metadata.get('status', 'wartet_auf_bearbeitung')}",
                "",
                "Hinweis: Automatisch ausgefuehrt werden nur sichere Ablage-/Sortieraufgaben.",
                "Analyse oder riskante Aktionen werden zur spaeteren Bearbeitung vorgemerkt.",
            ]
        )
    )

    subprocess.run(
        ["/usr/sbin/sendmail", "-i", "-f", AUTOREPLY_FROM, target],
        input=response.as_bytes(),
        check=True,
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--original-recipient", default="")
    parser.add_argument("--sender", default="")
    args = parser.parse_args()

    message_bytes = sys.stdin.buffer.read()
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    received_at = datetime.now().astimezone()

    from_name, from_addr = parseaddr(message.get("From", ""))
    sender = args.sender or from_addr or "unknown"
    reply_candidates = getaddresses(message.get_all("Reply-To", []) or message.get_all("From", []))
    reply_to = next((addr for _, addr in reply_candidates if addr), from_addr or sender)
    subject = str(message.get("Subject", ""))

    message_dir = create_message_dir(sender, received_at)
    attachments_dir = message_dir / "attachments"
    (message_dir / "mail.eml").write_bytes(message_bytes)

    body_text, body_html = extract_bodies(message)
    (message_dir / "body.txt").write_text(body_text + ("\n" if body_text else ""), encoding="utf-8")
    if body_html:
        (message_dir / "body.html").write_text(body_html + "\n", encoding="utf-8")

    attachments = save_attachments(message, attachments_dir)
    control_fields = parse_control_fields(body_text)
    status = "wartet_auf_bearbeitung"
    if control_fields.get("AKTION", "").lower() in {"speichern", "ablage", "ablegen"}:
        status = "eingegangen_und_abgelegt"

    metadata = {
        "received_at": received_at.isoformat(timespec="seconds"),
        "recipient": args.original_recipient or args.recipient,
        "router_recipient": args.recipient,
        "envelope_sender": args.sender,
        "from": {"name": from_name, "address": from_addr},
        "reply_to": reply_to,
        "subject": subject,
        "message_id": message.get("Message-ID"),
        "control_fields": control_fields,
        "attachments": attachments,
        "status": status,
    }
    topic_index = write_topic_index(message_dir, control_fields, subject, received_at)
    if topic_index:
        metadata["topic_index"] = topic_index

    (message_dir / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (message_dir / "status.txt").write_text(f"STATUS: {status}\n", encoding="utf-8")
    (message_dir / "auftrag.md").write_text(
        "\n".join(
            [
                f"# KI-Mailauftrag: {subject or '(ohne Betreff)'}",
                "",
                f"- Eingang: {received_at.isoformat(timespec='seconds')}",
                f"- Von: {from_addr or sender}",
                f"- Empfaenger: {args.original_recipient or args.recipient}",
                f"- Status: {status}",
                f"- AKTION: {control_fields.get('AKTION', 'nicht angegeben')}",
                f"- THEMA: {control_fields.get('THEMA', 'nicht angegeben')}",
                f"- ZIEL: {control_fields.get('ZIEL', 'nicht angegeben')}",
                f"- AUFGABE: {control_fields.get('AUFGABE', 'nicht angegeben')}",
                "",
                "## Anhaenge",
                *(f"- {item['saved_name']} ({item['size']} Bytes)" for item in attachments),
                *( ["- keine"] if not attachments else [] ),
                "",
                "## Mailtext",
                body_text or "(kein Textinhalt erkannt)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    autoresponse_error = None
    autoresponse_sent_to = None
    try:
        autoresponse_sent_to = send_autoresponse(message, reply_to, message_dir, metadata, attachments)
    except subprocess.CalledProcessError as exc:
        autoresponse_error = f"sendmail failed rc={exc.returncode}"

    fragments = [
        f"ki-router recipient={args.recipient}",
        f"orig_recipient={args.original_recipient or args.recipient}",
        f"sender={sender}",
        f"dir={message_dir}",
        f"attachments={len(attachments)}",
        f"status={status}",
    ]
    if autoresponse_sent_to:
        fragments.append(f"autoresponse_to={autoresponse_sent_to}")
    if autoresponse_error:
        fragments.append(f"autoresponse_error={autoresponse_error}")
    print(" ".join(fragments), file=sys.stdout, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
