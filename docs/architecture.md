# Architecture

## Components

### Mail containers

- `mailin-postfix` accepts mail and routes selected recipients to router scripts.
- `mailin-dovecot` provides mailbox-related runtime support.

### Router scripts

- `router/factcheck_router.py` handles Faketest mails and publication replies.
- It detects publication replies via the `FT-PUB <job-id> <token>` marker and writes a `publish_request.json` into the matching job directory.

### Worker

- `host-tools/faketest-worker.py` is run by systemd on the host.
- It processes saved jobs, extracts attachment text, performs research/LLM calls, sends result mails and publishes approved facts checks.

### WordPress publication

- Public label: `Faktencheck`.
- Internal label: `Faketest`.
- Approved results are published as WordPress pages under `/faktencheck/`.
- Live publication follows the existing Staging → Git → Main → Live promote flow.

## Important separation of responsibilities

- m00h runs the Faketest worker and Staging WordPress runtime.
- m11h hosts Git worktrees and Live WordPress runtime.
- A local `127.0.0.1:<port>` check must run on the host that owns that runtime.
  - Staging: m00h, usually `127.0.0.1:20001`.
  - Live: m11h, usually `127.0.0.1:20000`.

## Known historical failure modes

- Bifrost/LLM returned tool calls or timed out; worker now disables tool calls and streams responses.
- Binary links from HTML mails were decoded as UTF-8; worker now skips likely binary URLs.
- OCR via Tesseract timed out; worker now treats subprocess timeouts as normal command failures.
- Video attachments/direct video file URLs are handled via `ffprobe`/`ffmpeg` plus a configurable transcription command. Missing video tooling or transcription yields extraction warnings, not worker crashes.
- Live checks were previously attempted from the wrong host; Live checks must run on `publish.live_release_host`.
- Release script merged a stale local `dev`; it must merge `origin/dev` into `main`.
- Cloudflare may serve stale 404 after a successful Live promote; purge and re-check public URL.
