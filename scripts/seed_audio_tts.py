"""Seed-Audio text-to-audio (SFX, music, voice) through the Doubao V3 HTTP endpoint."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

from studio_runtime import ROOT, activate_runtime, data_dir, find_executable
from voice_settings import VoiceConfigError, private_write, windows_protect

URL = "https://openspeech.bytedance.com/api/v3/tts/create"
DEFAULT_MODEL = "seed-audio-1.0"
RESOURCE_IDS = {"seed-audio-1.0"}
FORMATS = {"mp3", "wav", "pcm"}
SAMPLE_RATES = {16000, 24000, 44100, 48000}
MAX_TEXT = 5000
MAX_RESPONSE = 64 * 1024 * 1024


class SeedAudioError(RuntimeError):
    """Sanitized failure; status keeps billing claims honest for rejected requests."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def secret_path() -> Path:
    name = "seed-audio-key.dpapi" if os.name == "nt" else "seed-audio-key.secret"
    return (data_dir() / name).expanduser().resolve()


def save_api_key(value: str) -> None:
    value = value.strip()
    if not value or len(value) > 65536 or any(c.isspace() for c in value):
        raise VoiceConfigError("The speech API key must be a nonempty single token")
    payload = value.encode("utf-8")
    private_write(secret_path(), windows_protect(payload) if os.name == "nt" else payload)


def api_key_present() -> bool:
    return bool(os.environ.get("SEED_AUDIO_API_KEY", "").strip()) or secret_path().is_file()


def read_api_key() -> str:
    value = os.environ.get("SEED_AUDIO_API_KEY", "").strip()
    if value:
        return value
    path = secret_path()
    if not path.is_file():
        raise SeedAudioError("Configure SEED_AUDIO_API_KEY or a local Seed-Audio credential")
    payload = path.read_bytes()
    return (windows_protect(payload, decrypt=True) if os.name == "nt" else payload).decode("utf-8").strip()


def guarded_output(path: Path) -> Path:
    """Media products belong to the project, never to the skill source."""
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(ROOT):
        raise SeedAudioError("Output must stay outside the skill directory")
    return resolved


def validate(*, model: str, resource_id: str, audio_format: str, sample_rate: int,
             pitch_rate: int, speech_rate: int, loudness_rate: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", model):
        raise SeedAudioError("Model must be a plain model ID")
    if resource_id not in RESOURCE_IDS:
        raise SeedAudioError("Unsupported resource ID; select seed-audio-1.0")
    if audio_format not in FORMATS:
        raise SeedAudioError("Format must be mp3, wav or pcm")
    if sample_rate not in SAMPLE_RATES:
        raise SeedAudioError("Sample rate must be 16000, 24000, 44100 or 48000")
    for name, value in (("pitch", pitch_rate), ("speech", speech_rate), ("loudness", loudness_rate)):
        if type(value) is not int or not -50 <= value <= 100:
            raise SeedAudioError(f"The {name} rate must be an integer in -50..100")


def request_audio(text: str, settings: dict, key: str, timeout: int) -> tuple[bytes, dict]:
    body = json.dumps({
        "model": settings["model"],
        "text_prompt": text,
        "audio_config": {
            "format": settings["format"],
            "sample_rate": settings["sample_rate"],
            "pitch_rate": settings["pitch_rate"],
            "speech_rate": settings["speech_rate"],
            "loudness_rate": settings["loudness_rate"],
        },
        "watermark": {},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        # The gateway resolves the key by resource, so this header is part of auth.
        "X-Api-Key": key,
        "X-Api-Resource-Id": settings["resource_id"],
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            failure = json.loads(exc.read(4096).decode("utf-8", "replace"))
            if isinstance(failure, dict):
                detail = f" (code {failure.get('code')}: {str(failure.get('message'))[:160]})"
        except (ValueError, OSError):
            pass
        raise SeedAudioError(f"Seed-Audio returned HTTP {exc.code}{detail}", status=exc.code) from None
    except urllib.error.URLError as exc:
        raise SeedAudioError(f"Seed-Audio network failure: {exc.reason}") from None
    if len(payload) > MAX_RESPONSE:
        raise SeedAudioError("Seed-Audio response exceeded the size limit")
    try:
        result = json.loads(payload.decode("utf-8"))
    except ValueError:
        raise SeedAudioError("Seed-Audio returned a non-JSON body") from None
    if not isinstance(result, dict) or "audio" not in result:
        code = result.get("code") if isinstance(result, dict) else None
        message = str(result.get("message"))[:160] if isinstance(result, dict) else ""
        raise SeedAudioError(f"Seed-Audio response has no audio (code {code}: {message})")
    try:
        audio = base64.b64decode(str(result["audio"]), validate=True)
    except (binascii.Error, ValueError):
        raise SeedAudioError("Seed-Audio returned malformed base64 audio") from None
    if not audio:
        raise SeedAudioError("Seed-Audio returned empty audio")
    return audio, result


def probe(path: Path) -> dict:
    ffprobe = find_executable("ffprobe")
    if not ffprobe:
        return {"structure_verified": False, "reason": "ffprobe is unavailable"}
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                                 "format=duration,size:stream=codec_name,sample_rate,channels",
                                 "-of", "json", str(path)],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        if result.returncode:
            return {"structure_verified": False, "reason": "ffprobe could not parse the output"}
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        container = data.get("format") or {}
        return {"structure_verified": True,
                "codec": stream.get("codec_name"),
                "sample_rate": int(stream.get("sample_rate") or 0),
                "channels": int(stream.get("channels") or 0),
                "duration": float(container.get("duration") or 0),
                "bytes": int(container.get("size") or path.stat().st_size)}
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"structure_verified": False, "reason": "ffprobe failed"}


def write_atomic(path: Path, payload: bytes) -> None:
    partial = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    try:
        with partial.open("xb") as output:
            output.write(payload)
        if path.exists():
            raise SeedAudioError("Output exists; reuse it or select a new version")
        if os.name == "nt":
            partial.rename(path)
        else:
            os.link(partial, path)
            partial.unlink()
    finally:
        partial.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "configure", "generate"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text-file", type=Path)
    source.add_argument("--text")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--resource-id", default=DEFAULT_MODEL)
    parser.add_argument("--format", choices=sorted(FORMATS), default="mp3")
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--pitch-rate", type=int, default=0)
    parser.add_argument("--speech-rate", type=int, default=0)
    parser.add_argument("--loudness-rate", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--key-stdin", action="store_true", help="Save a key read from private stdin")
    parser.add_argument("--confirm-billable", action="store_true", help="Confirm this request may be billed")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-url", action="store_true", help="Include the signed CDN link in the report")
    args = parser.parse_args()

    settings = {"model": args.model, "resource_id": args.resource_id, "format": args.format,
                "sample_rate": args.sample_rate, "pitch_rate": args.pitch_rate,
                "speech_rate": args.speech_rate, "loudness_rate": args.loudness_rate}
    paid_attempt = False
    try:
        validate(model=args.model, resource_id=args.resource_id, audio_format=args.format,
                 sample_rate=args.sample_rate, pitch_rate=args.pitch_rate,
                 speech_rate=args.speech_rate, loudness_rate=args.loudness_rate)
        if args.action == "configure":
            if not args.key_stdin:
                raise SeedAudioError("Provide --key-stdin so the key never appears in command arguments")
            save_api_key(sys.stdin.readline(65538))
        if args.action in {"check", "configure"}:
            report = {"ready": api_key_present(), "api_key_present": api_key_present(),
                      "resource_id": args.resource_id, "model": args.model,
                      "endpoint": URL, "network_verified": False, "billable_request_sent": False}
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ready"] else 1

        if args.text_file:
            text = args.text_file.read_text(encoding="utf-8-sig")
        elif args.text:
            text = args.text
        else:
            raise SeedAudioError("Provide --text-file or --text")
        text = text.strip()
        if not text:
            raise SeedAudioError("The text prompt is empty")
        if len(text) > MAX_TEXT:
            raise SeedAudioError(f"The text prompt exceeds {MAX_TEXT} characters")
        if not args.output:
            raise SeedAudioError("--output is required")
        output = guarded_output(args.output)
        if output.suffix.lower() != "." + args.format:
            raise SeedAudioError(f"Output must use the .{args.format} extension")
        if output.exists():
            raise SeedAudioError("Output exists; reuse it or select a new version")
        report = {"model": args.model, "format": args.format, "characters": len(text),
                  "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  "protocol": "doubao-v3-http-create"}
        if args.dry_run:
            print(json.dumps(dict(report, network=False, billable_request_sent=False), ensure_ascii=False))
            return 0
        if not args.confirm_billable:
            raise SeedAudioError("Confirm the prompt with the user, then pass --confirm-billable")
        key = read_api_key()
        output.parent.mkdir(parents=True, exist_ok=True)
        paid_attempt = True
        audio, result = request_audio(text, settings, key, args.timeout)
        write_atomic(output, audio)
        structure = probe(output)
        report.update(structure, output=str(output), audio_sha256=hashlib.sha256(audio).hexdigest(),
                      provider_duration=result.get("duration"), listening_verified=False,
                      sign_verified=False)
        if args.print_url and result.get("url"):
            report["download_url"] = result["url"]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (SeedAudioError, VoiceConfigError, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, (SeedAudioError, VoiceConfigError)) else \
            "Seed-Audio generation failed; inspect credentials, quota, network or the output path"
        billed = paid_attempt and (getattr(exc, "status", None) is None or getattr(exc, "status", 500) >= 500)
        print(json.dumps({"ready": False, "error": message,
                          "request_may_have_been_billed": billed,
                          "automatic_retry": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    activate_runtime()
    raise SystemExit(main())
