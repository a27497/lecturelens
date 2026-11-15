"""Download/rebuild only pinned public assets; never calls a model API."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url, path, expected, download):
    if not path.exists():
        if not download:
            raise ValueError(f"Missing asset {path}; use --download")
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--retry",
                "2",
                "--max-time",
                "900",
                "--output",
                str(partial),
                url,
            ],
            check=True,
        )
        if digest(partial) != expected:
            raise ValueError("Downloaded bytes differ from freeze; refuse replacement")
        partial.rename(path)
    if digest(path) != expected:
        raise ValueError(f"Frozen asset hash mismatch: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((REPORT / "assets.lock.json").read_text())
    for source in manifest["sources"]:
        media = ROOT / source["video_file"]
        fetch(source["video_url"], media, source["video_sha256"], args.download)
        fetch(
            source["captions_url"],
            ROOT / source["captions_file"],
            source["captions_sha256"],
            args.download,
        )
        target = ROOT / source["evaluation_video_file"]
        if not target.exists():
            if not args.download:
                raise ValueError("Missing subtitle-free input; use --download")
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(media),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-c",
                    "copy",
                    "-sn",
                    "-dn",
                    str(target),
                ],
                check=True,
            )
        if digest(target) != source["evaluation_video_sha256"]:
            raise ValueError(
                "Remux hash mismatch; use the recorded ffmpeg build, never rewrite the lock"
            )
        print(source["id"], source["duration_ms"], "ms", "hashes verified")
    print(
        json.dumps(
            {
                "lectures": manifest["lecture_count"],
                "total_duration_ms": manifest["total_duration_ms"],
            }
        )
    )


if __name__ == "__main__":
    main()
