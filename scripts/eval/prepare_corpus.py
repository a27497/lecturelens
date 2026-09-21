#!/usr/bin/env python3
"""Download the pinned pilot corpus and verify local media without model calls.

Requires Python 3.11+, curl and ffprobe. Media stays in gitignored .data/.
"""
import argparse
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "eval/pilot-v1/sources.json"
LOCK = ROOT / "eval/pilot-v1/assets.lock.json"
DATA = ROOT / ".data/eval/pilot-v1"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, path, expected, verify_only):
    if not path.exists():
        if verify_only:
            raise ValueError(f"Missing asset: {path}")
        partial = path.with_suffix(path.suffix + ".part")
        subprocess.run([
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--retry", "3", "--connect-timeout", "30", "--max-time", "600",
            "--output", str(partial), url,
        ], check=True)
        if expected and digest(partial) != expected["sha256"]:
            raise ValueError(f"Downloaded content differs from lock: {url}")
        partial.replace(path)
    result = {"bytes": path.stat().st_size, "sha256": digest(path)}
    if expected and result != expected:
        raise ValueError(f"Asset differs from lock (not overwritten): {path}")
    return result


def millis(value):
    parts = value.split(":")
    return round(sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts))) * 1000)


def parse_captions(path, source_id, duration_ms):
    content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if not content.startswith("WEBVTT"):
        raise ValueError(f"Not WebVTT: {path}")
    cues = []
    for block in re.split(r"\n\s*\n", content):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = re.fullmatch(r"([\d:.]+)\s+-->\s+([\d:.]+)(?:\s+.*)?", line)
            if not match:
                continue
            start, end = map(millis, match.groups())
            text = html.unescape(re.sub(r"<[^>]*>", "", " ".join(lines[index + 1:]))).strip()
            if not (0 <= start < end <= duration_ms + 2000) or not text:
                raise ValueError(f"Invalid caption bounds/text in {path}: {line}")
            if cues and start < cues[-1]["start_ms"]:
                raise ValueError(f"Unsorted captions: {path}")
            cues.append({"reference_id": f"{source_id}:caption:{len(cues) + 1:04d}",
                         "start_ms": start, "end_ms": end, "text": text})
            break
    if not cues:
        raise ValueError(f"No captions: {path}")
    return cues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="No network; validate existing assets")
    parser.add_argument("--write-lock", action="store_true", help="Create initial lock; refuses to overwrite")
    args = parser.parse_args()
    if args.write_lock and LOCK.exists():
        parser.error("Lock already exists; review asset changes manually")
    if args.write_lock and args.verify_only:
        parser.error("--write-lock and --verify-only are mutually exclusive")
    if not LOCK.exists() and not args.write_lock:
        parser.error("Initial download requires --write-lock")
    manifest = json.loads(MANIFEST.read_text())
    pinned = json.loads(LOCK.read_text())["sources"] if LOCK.exists() else {}
    sources = manifest["sources"]
    ids = [source["id"] for source in sources]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z0-9-]+", id) for id in ids):
        raise ValueError("Invalid or duplicate source IDs")
    if pinned and set(pinned) != set(ids):
        raise ValueError("Source list differs from lock")
    splits = {}
    result = {}
    for source in sources:
        course, split = source["course_id"], source["split"]
        if split not in ("dev", "holdout") or splits.setdefault(course, split) != split:
            raise ValueError(f"Invalid split or course leakage: {course}")
        id = source["id"]
        directory = DATA / id
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Preparing {id} ({split})", flush=True)
        assets = {}
        for name, url_key in (("video.mp4", "video_url"), ("captions.en.vtt", "captions_url")):
            url = source[url_key]
            expected_asset = pinned.get(id, {}).get("assets", {}).get(name)
            if expected_asset and expected_asset["url"] != url:
                raise ValueError(f"Source URL differs from lock: {id}/{name}")
            expected = {k: expected_asset[k] for k in ("bytes", "sha256")} if expected_asset else None
            assets[name] = {"url": url, **download(url, directory / name, expected, args.verify_only)}
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
            str(directory / "video.mp4"),
        ]))
        videos = [s for s in probe["streams"] if s["codec_type"] == "video"]
        audios = [s for s in probe["streams"] if s["codec_type"] == "audio"]
        duration_ms = round(float(probe["format"]["duration"]) * 1000)
        if not videos or not audios or duration_ms <= 0:
            raise ValueError(f"Missing playable audio/video: {id}")
        cues = parse_captions(directory / "captions.en.vtt", id, duration_ms)
        (directory / "reference-captions.jsonl").write_text(
            "".join(json.dumps(cue, ensure_ascii=False) + "\n" for cue in cues), encoding="utf-8")
        result[id] = {"assets": assets, "duration_ms": duration_ms,
                      "width": videos[0]["width"], "height": videos[0]["height"],
                      "video_codec": videos[0]["codec_name"], "audio_codec": audios[0]["codec_name"],
                      "caption_count": len(cues), "caption_end_ms": cues[-1]["end_ms"]}
        print(f"Verified {id}: {duration_ms / 60000:.1f} min, {len(cues)} captions", flush=True)
    report = {"version": manifest["version"], "checked_at": datetime.now(timezone.utc).isoformat(),
              "sources": result, "annotation_status": "not_started",
              "note": "Container/hash/timestamp checks only; semantic caption alignment needs review."}
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.write_lock:
        LOCK.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Ready: {DATA}", flush=True)


if __name__ == "__main__":
    main()
