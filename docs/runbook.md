# Runbook

## Check worker health

```bash
ssh m00h 'systemctl is-enabled faketest-worker.timer && systemctl is-active faketest-worker.timer'
ssh m00h 'systemctl status faketest-worker.service --no-pager -l'
```

## Retry one failed job

Only retry after understanding the failure. Add a clear note to `meta.json` and set the status back to `freigegeben` or the publish request to `retry`, depending on the failure stage.

Common stages:

- content generation failed → set job status to `freigegeben` after fixing the cause.
- publication failed → set `publish_request.json.status` and `meta.publish_status` to `retry`.

## Publication blocked by dirty Staging

Check m00h Staging runtime:

```bash
ssh m00h 'cd /home/chris/web/staging.afd-im-netz.de && git status --short && git rev-parse HEAD && git rev-parse origin/dev'
```

Rules:

- Do not blindly delete unknown files.
- `wp-content/upgrade/` is usually a WordPress runtime leftover and can be moved to `/tmp/opencode/...` after inspection.
- If a file is tracked in `origin/dev` but untracked locally, m00h is probably behind and should be synced to `origin/dev` if clean.

## Publication appears Live-blocked but page is public

Check both local Live and public Cloudflare path:

```bash
curl -H 'Host: afd-im-netz.de' -H 'X-Forwarded-Proto: https' http://127.0.0.1:20000/faktencheck/<slug>/
curl -L https://afd-im-netz.de/faktencheck/<slug>/
```

If local is 200 but public is 404, purge Cloudflare and re-check.

## WPeMatico alert handling

1. Read the referenced JSON snapshot.
2. If it reports dedupe candidates, run a fresh dry-run before deleting anything.
3. Only delete posts that still appear in the fresh dry-run.
4. Run a fresh monitoring snapshot afterwards.

Example:

```bash
docker compose -f compose.yml -f compose.live.yml run --rm wpcli wpematico-search-m00h dedupe --dry-run --mode=all --format=json
scripts/wpematico-monitoring-snapshot.sh --profile live --format=json
```

## Settings permissions

The worker runs as user/group `chris` on m00h. Runtime settings must be readable by that user, e.g.:

```bash
sudo chown root:chris /etc/faketest/settings.json
sudo chmod 0640 /etc/faketest/settings.json
```
