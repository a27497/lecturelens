"""Verify full duration, removed subtitles and unchanged encoded AV packets."""

import json
import subprocess

from score import REPORT, ROOT


def inspect(path):
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,start_time,duration,time_base,duration_ts",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(output)


def packets(path, kind):
    return subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:" + kind + ":0",
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        text=True,
    ).strip()


def main():
    manifest = json.loads((REPORT / "assets.lock.json").read_text())
    results = []
    for source in manifest["sources"]:
        original = ROOT / source["video_file"]
        target = ROOT / source["evaluation_video_file"]
        before, after = inspect(original), inspect(target)
        assert (
            abs(float(before["format"]["duration"]) * 1000 - source["duration_ms"]) <= 1
        )
        before_audio = next(s for s in before["streams"] if s["codec_type"] == "audio")
        after_audio = next(s for s in after["streams"] if s["codec_type"] == "audio")
        assert before_audio == after_audio, "Audio timing or sample count changed"
        assert not any(s["codec_type"] == "subtitle" for s in after["streams"])
        measured = {}
        for name, kind in (("audio", "a"), ("video", "v")):
            measured[name] = packets(original, kind)
            assert measured[name] == packets(target, kind), (source["id"], name)
            assert measured[name] == source["stream_sha256"][name]
        results.append(
            {
                "source_id": source["id"],
                "original_duration_seconds": before["format"]["duration"],
                "evaluation_duration_seconds": after["format"]["duration"],
                "container_duration_delta_seconds": float(after["format"]["duration"])
                - float(before["format"]["duration"]),
                "audio_timing_unchanged": before_audio,
                "evaluation_subtitle_streams": 0,
                "stream_sha256": measured,
            }
        )
    print(
        json.dumps(
            {
                "ffmpeg": subprocess.check_output(
                    ["ffmpeg", "-version"], text=True
                ).splitlines()[0],
                "verified_lectures": len(results),
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
