#!/usr/bin/env python3
"""Download pinned, openly licensed course media and make captioned evaluation clips."""

import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".data/l22-eval/sources"


def millis(value):
    h, m, s = value.split(":")
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def timestamp(value):
    seconds, ms = divmod(value, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "eval/study-v1/sources.json").read_text())
    results = []
    for source in manifest["sources"]:
        for ext, field in [("mp4", "video_url"), ("vtt", "subtitle_url")]:
            path = OUT / f"{source['id']}.{ext}"
            if not path.exists():
                with urllib.request.urlopen(source[field], timeout=60) as response, path.open("wb") as dest:
                    while chunk := response.read(1024 * 1024):
                        dest.write(chunk)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"][ext], path
        blocks = (OUT / f"{source['id']}.vtt").read_text().split("\n\n")
        for clip in source["clips"]:
            start, end = clip["start_seconds"] * 1000, clip["end_seconds"] * 1000
            captions = []
            for block in blocks:
                match = re.search(r"(\d\d:\d\d:\d\d\.\d+) --> (\d\d:\d\d:\d\d\.\d+)", block)
                if match and millis(match[1]) < end and millis(match[2]) > start:
                    captions.append(
                        f"{len(captions) + 1}\n{timestamp(max(0, millis(match[1]) - start))} --> {timestamp(min(end, millis(match[2])) - start)}\n{block[match.end() :].strip()}\n"
                    )
            assert captions
            subtitle, video = OUT / f"{clip['id']}.srt", OUT / f"{clip['id']}.mp4"
            subtitle.write_text("\n".join(captions))
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    str(start / 1000),
                    "-i",
                    str(OUT / f"{source['id']}.mp4"),
                    "-i",
                    str(subtitle),
                    "-t",
                    str((end - start) / 1000),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-map",
                    "1:0",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-threads",
                    "2",
                    "-c:a",
                    "aac",
                    "-c:s",
                    "mov_text",
                    "-metadata:s:s:0",
                    "language=eng",
                    str(video),
                ],
                check=True,
            )
            results.append(
                {
                    "id": clip["id"],
                    "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                    "source_offset_ms": start,
                }
            )
            print("Prepared", clip["id"], flush=True)
    (OUT / "clips.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
