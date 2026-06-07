#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(command: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(command, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or exc.output or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return 124, str(stdout), (str(stderr).strip() + "\nTimeout after %s seconds" % timeout).strip()


def read_text_outputs(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.exists() and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                chunks.append(text)
    return "\n\n".join(chunks).strip()


def run_shell_template(template: str, audio: Path, timeout: int) -> tuple[bool, str, str]:
    command = template.format(audio=shlex.quote(str(audio)), audio_path=shlex.quote(str(audio)))
    rc, out, err = run_command(["bash", "-lc", command], timeout)
    if rc == 0 and out.strip():
        return True, out.strip(), ""
    return False, "", (err or out or "rc=%s" % rc).strip()


def try_openai_whisper(audio: Path, language: str, model: str, timeout: int, workdir: Path) -> tuple[bool, str, str]:
    exe = shutil.which("whisper")
    if not exe:
        return False, "", "whisper CLI not found"
    out_dir = workdir / "whisper-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [exe, "--language", language, "--model", model, "--output_format", "txt", "--output_dir", str(out_dir), str(audio)]
    rc, out, err = run_command(command, timeout)
    text = read_text_outputs(list(out_dir.glob("*.txt"))) or out.strip()
    if rc == 0 and text:
        return True, text, ""
    return False, "", (err or out or "rc=%s" % rc).strip()


def try_whisper_ctranslate2(audio: Path, language: str, model: str, timeout: int, workdir: Path) -> tuple[bool, str, str]:
    exe = shutil.which("whisper-ctranslate2")
    if not exe:
        return False, "", "whisper-ctranslate2 not found"
    out_dir = workdir / "whisper-ctranslate2-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [exe, "--language", language, "--model", model, "--output_format", "txt", "--output_dir", str(out_dir), str(audio)]
    rc, out, err = run_command(command, timeout)
    text = read_text_outputs(list(out_dir.glob("*.txt"))) or out.strip()
    if rc == 0 and text:
        return True, text, ""
    return False, "", (err or out or "rc=%s" % rc).strip()


def try_faster_whisper_python(audio: Path, language: str, model: str, timeout: int, workdir: Path) -> tuple[bool, str, str]:
    # The faster-whisper Python API does not expose a simple subprocess-level
    # timeout. This backend is therefore tried after fast CLI backends and relies
    # on the caller/systemd timeout for hard cancellation.
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as exc:
        return False, "", "faster_whisper Python module not available: %s" % exc.__class__.__name__
    try:
        compute_type = os.environ.get("FAKETEST_TRANSCRIBE_COMPUTE_TYPE", "int8")
        device = os.environ.get("FAKETEST_TRANSCRIBE_DEVICE", "cpu")
        cpu_threads = int(os.environ.get("FAKETEST_TRANSCRIBE_CPU_THREADS", "2") or "2")
        whisper = WhisperModel(model, device=device, compute_type=compute_type, cpu_threads=cpu_threads)
        segments, info = whisper.transcribe(str(audio), language=language, beam_size=1, vad_filter=True)
        lines: list[str] = []
        for segment in segments:
            text = (getattr(segment, "text", "") or "").strip()
            if text:
                lines.append("[%s-%s] %s" % (format_ts(float(segment.start)), format_ts(float(segment.end)), text))
        transcript = "\n".join(lines).strip()
        if transcript:
            return True, transcript, ""
        return False, "", "faster_whisper produced no transcript"
    except Exception as exc:
        return False, "", "faster_whisper failed: %s: %s" % (exc.__class__.__name__, str(exc)[:200])


def format_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


def try_whisper_cpp(audio: Path, language: str, model: str, timeout: int, workdir: Path) -> tuple[bool, str, str]:
    exe = shutil.which("whisper-cli") or shutil.which("whisper.cpp") or shutil.which("main")
    if not exe:
        return False, "", "whisper.cpp CLI not found"
    model_path = os.environ.get("FAKETEST_WHISPER_CPP_MODEL") or model
    out_base = workdir / "whispercpp-output"
    command = [exe, "-m", model_path, "-f", str(audio), "-l", language, "-otxt", "-of", str(out_base)]
    rc, out, err = run_command(command, timeout)
    text = read_text_outputs([Path(str(out_base) + ".txt")]) or out.strip()
    if rc == 0 and text:
        return True, text, ""
    return False, "", (err or out or "rc=%s" % rc).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Faketest audio transcription wrapper. Writes transcript to stdout.")
    parser.add_argument("audio", help="Audio file path, usually WAV extracted by ffmpeg")
    parser.add_argument("--language", default=os.environ.get("FAKETEST_TRANSCRIBE_LANGUAGE", "de"))
    parser.add_argument("--model", default=os.environ.get("FAKETEST_TRANSCRIBE_MODEL", "small"))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("FAKETEST_TRANSCRIBE_TIMEOUT", "900")))
    parser.add_argument("--workdir", default=os.environ.get("FAKETEST_TRANSCRIBE_WORKDIR", "/tmp/faketest-transcribe"))
    parser.add_argument("--command", default=os.environ.get("FAKETEST_TRANSCRIBE_COMMAND", ""), help="Optional shell template. Supports {audio}/{audio_path}.")
    args = parser.parse_args()

    audio = Path(args.audio)
    if not audio.exists() or not audio.is_file():
        print("Audio file not found: %s" % audio, file=sys.stderr)
        return 2

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    if args.command.strip():
        ok, text, err = run_shell_template(args.command, audio, args.timeout)
        if ok:
            print(text)
            return 0
        errors.append("custom command: " + err)

    for label, fn in [
        ("whisper", try_openai_whisper),
        ("whisper-ctranslate2", try_whisper_ctranslate2),
        ("faster-whisper-python", try_faster_whisper_python),
        ("whisper.cpp", try_whisper_cpp),
    ]:
        ok, text, err = fn(audio, args.language, args.model, args.timeout, workdir)
        if ok:
            print(text)
            return 0
        errors.append("%s: %s" % (label, err))

    print("No usable transcription backend produced text.", file=sys.stderr)
    for error in errors:
        print("- " + error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
