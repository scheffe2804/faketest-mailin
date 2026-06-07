# Faktencheck Publishing Flow

## Public/private naming

- Internal workflow and mail address: `Faketest`.
- Public WordPress section: `Faktencheck`.

## Approval by reply mail

Result mails include a subject marker:

```text
[FT-PUB <job-id> <token>]
```

A reply from the configured allowed sender means: publish this facts check.

Non-reply means: keep it internal/unpublished.

## Public content rules

- Do not expose sender address, original private filenames, internal paths or job metadata.
- Do not publish third-party images/videos by default.
- For image cases, publish OCR/description and rights notice rather than copying the image.
- Keep sources linked and `[n]` references anchored to the source list.

## Required page structure

- Clear title and slug under `/faktencheck/`.
- `Kurzfazit` near the top.
- `Gesamtbewertung` directly after `Kurzfazit`.
- Structured labels:
  - `Tatsachenkern:`
  - `Framing/Wirkung:`
  - `Absicht:`
  - `Kritischer Befund:`
- Source list with anchors `quelle-1`, `quelle-2`, ...
