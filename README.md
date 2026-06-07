# Faketest Mailin

Mail-in based fact-checking automation for incoming mails, attachments and publication requests.

The public product name is **Faktencheck**; the internal mail/workflow name remains **Faketest**.

## What this repository contains

- `router/` — mail router scripts that classify incoming mails and publication replies.
- `host-tools/faketest-worker.py` — worker that extracts content, calls the LLM/research pipeline, sends result mails and publishes approved facts checks to WordPress.
- `host-tools/*.service` / `*.timer` — systemd units for worker and cleanup jobs.
- `config/postfix/` — Postfix routing/access maps.
- `config/faketest/settings.example.json` — sanitized example settings.
- `docker-compose.yml`, `postfix/`, `dovecot/` — mail-in runtime container definitions.
- `docs/` — architecture and operations notes.

## What must not be committed

Never commit real runtime data or secrets:

- real `config/faketest/settings.json`
- mail archives, Faketest jobs, attachments, extracted OCR/transcripts
- `.env` files, certificates, private keys, API tokens
- `/srv/tailshare/Faketest-Mails` or `/srv/mailin/*` runtime data

See `.gitignore`.

## Runtime topology

Current production topology is split across hosts:

- m00h: mail intake, Faketest worker runtime, Staging WordPress runtime.
- m11h: Git source/worktrees and Live WordPress runtime.
- The worker delegates release operations to the configured `publish.live_release_host`.

The worker must distinguish:

- Staging local HTTP checks on the Staging runtime host.
- Live local HTTP checks on the Live runtime host.
- Git source state on the Git host/worktrees.

## Basic deployment pattern

1. Edit and test files in this repository.
2. Copy `host-tools/faketest-worker.py` to `/usr/local/sbin/faketest-worker.py` on m00h.
3. Copy/sync systemd units if changed.
4. Keep real settings outside Git, e.g. `/etc/faketest/settings.json`.
5. Run a Python syntax check and verify the systemd timer.

Example:

```bash
python3 -m py_compile host-tools/faketest-worker.py
scp host-tools/faketest-worker.py m00h:/tmp/faketest-worker.py
ssh m00h 'sudo install -m 0755 /tmp/faketest-worker.py /usr/local/sbin/faketest-worker.py'
```

Preferred operational deployment:

```bash
scripts/deploy-worker.sh
```

Deploy real runtime settings only when explicitly intended:

```bash
scripts/deploy-worker.sh --settings
```

## Operational helpers

List current publish blockers while ignoring historical backup directories:

```bash
scripts/check-jobs.py --mode publish
```

Prepare one approved publication request for retry:

```bash
scripts/retry-publish.py <job-id> --reason "why this retry is safe"
```

## Publication flow

1. Incoming mail is archived and processed.
2. Worker generates a Faketest result mail with a publish token.
3. A reply from the configured allowed sender with `[FT-PUB <job-id> <token>]` creates a `publish_request.json`.
4. Worker creates/updates a Staging WordPress page under `/faktencheck/`.
5. Worker runs checks, commits release trigger changes, merges to `main`, deploys/promotes to Live, purges cache, verifies Live.

## Video fact-checking

The worker has a first controlled video-processing path for video attachments and direct public video file URLs. It reads metadata with `ffprobe`, extracts audio with `ffmpeg`, then calls the configured `video.transcribe_command`. `host-tools/faketest-transcribe.py` is a wrapper for Whisper-compatible backends. If no backend is installed, the worker records an extraction warning instead of crashing.

Platform/page downloads via `yt-dlp`, frame OCR and timestamped claim extraction are planned follow-up work.

## Video fact-checking plan

Video support is planned as an extension. See `docs/video-factcheck-plan.md`.
