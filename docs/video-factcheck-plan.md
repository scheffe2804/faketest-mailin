# Video Fact-Check Plan

Goal: support facts checks for publicly available videos and user-supplied video attachments.

## Intended pipeline

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
