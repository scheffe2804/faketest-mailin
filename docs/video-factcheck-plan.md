# Video Fact-Check Plan

Goal: support facts checks for publicly available videos and user-supplied video attachments.

## Phase 1 pipeline

Implemented first step:

1. Accept video attachments with configured extensions (`.mp4`, `.mov`, `.m4v`, `.webm`, `.mkv`).
2. Accept direct public video file URLs with the same extensions.
3. Inspect metadata with `ffprobe`.
4. Extract mono 16 kHz WAV audio with `ffmpeg`.
5. Call a configurable transcription command via `video.transcribe_command`, typically `faketest-transcribe.py`.
6. Feed video metadata and transcript into the normal Faketest pipeline.
7. If video tools or transcription are missing, return an extraction warning instead of crashing the worker.

The first implementation intentionally does **not** publish original video material, frames or thumbnails.

## Intended full pipeline

1. Accept video attachment or public video URL.
2. Verify source is permitted for internal analysis.
3. Download or stream video with strict limits.
4. Extract audio with `ffmpeg`.
5. Transcribe speech with Whisper or another speech-to-text engine.
6. Extract representative frames.
7. Run OCR on text overlays where useful.
8. Build time-coded claims.
9. Research claims against public sources.
10. Return a time-coded Faktencheck result by mail.

## Publication rule

Do not publish the original video, third-party frames or thumbnails by default. Public output should contain:

- video/source description
- relevant quoted transcript excerpts
- time markers
- claims and ratings
- source links

## Initial limits

Suggested first version:

- max video length: 20–30 minutes
- max file size: 500 MB to 1 GB
- max download time: configurable
- max extracted frames: configurable
- automatic timeout handling at each stage

## Tools

- `ffmpeg` for audio/frame extraction
- `yt-dlp` for permitted public video URLs
- Whisper or compatible speech-to-text tool
- Tesseract/OCR for text overlays

## Example transcription command

`video.transcribe_command` is a shell command template. The worker substitutes `{audio}` and `{audio_path}` with a shell-quoted WAV path.

Recommended wrapper command:

```json
"video": {
  "transcribe_command": "/opt/faketest-transcribe/venv/bin/python /usr/local/sbin/faketest-transcribe.py --language de --model small --timeout 900 {audio}"
}
```

The wrapper tries a custom command first if configured via `FAKETEST_TRANSCRIBE_COMMAND`, then known local backends:

- `whisper`
- `whisper-ctranslate2`
- Python module `faster_whisper`
- `whisper-cli` / `whisper.cpp` / `main`

The exact backend still has to be installed on the runtime host. The wrapper writes transcript text to stdout and diagnostics to stderr.

Install helper for a CPU-only faster-whisper venv:

```bash
scripts/install-faster-whisper.sh --prefix /opt/faketest-transcribe --model small
```

## Phase 2 candidates

- `yt-dlp` support for public platform/news pages that are not direct media files.
- Frame extraction and OCR of text overlays.
- Time-coded transcript chunks and claim-level timestamps.
- Better public-source attribution for embedded video pages.
