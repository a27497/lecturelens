#!/usr/bin/env python3
"""Generate a deterministic, synthetic course recording with FFmpeg.

Only Python's standard library is used.  The generated media is synthetic and is
written below the system temporary directory unless --output is supplied.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path


WIDTH = 1280
HEIGHT = 720
FPS = 12


FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
}


class Canvas:
    def __init__(self, width: int, height: int, color: tuple[int, int, int]):
        self.width = width
        self.height = height
        self.pixels = bytearray(color * (width * height))

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + width), min(self.height, y + height)
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        for py in range(y0, y1):
            start = (py * self.width + x0) * 3
            self.pixels[start : start + len(row)] = row

    def text(self, x: int, y: int, value: str, scale: int, color: tuple[int, int, int]) -> None:
        cursor = x
        for char in value.upper():
            if char == " ":
                cursor += 4 * scale
                continue
            glyph = FONT.get(char, FONT["-"])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        self.rect(cursor + gx * scale, y + gy * scale, scale, scale, color)
            cursor += 6 * scale

    def save_png(self, path: Path) -> None:
        raw = b"".join(
            b"\x00" + bytes(self.pixels[y * self.width * 3 : (y + 1) * self.width * 3])
            for y in range(self.height)
        )
        signature = b"\x89PNG\r\n\x1a\n"

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        path.write_bytes(
            signature
            + chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 7))
            + chunk(b"IEND", b"")
        )


def slide(title: str, lines: list[str], accent: tuple[int, int, int] = (31, 96, 190)) -> Canvas:
    image = Canvas(WIDTH, HEIGHT, (247, 249, 252))
    image.rect(0, 0, WIDTH, 96, accent)
    image.text(64, 25, title, 8, (255, 255, 255))
    image.rect(72, 142, 10, 460, accent)
    for index, line in enumerate(lines):
        image.text(120, 160 + index * 96, line, 6, (31, 41, 55))
    image.rect(1000, 590, 190, 54, (225, 234, 247))
    image.text(1025, 605, "COURSE 01", 4, accent)
    return image


def code_screen(stage: int) -> Canvas:
    image = Canvas(WIDTH, HEIGHT, (20, 25, 34))
    image.rect(0, 0, WIDTH, 62, (44, 52, 66))
    image.text(40, 17, "ADAPTIVE VIDEO PIPELINE", 4, (219, 226, 238))
    code = [
        "01  PUBLIC CLASS PIPELINE",
        "02  STATIC VOID PROBE VIDEO",
        "03  IF VIDEO RETURN METADATA",
        "04  FOR FRAME SCAN TIMELINE",
        "05  FILTER BLUR + BLACK",
        "06  DEDUP IMAGE + OCR",
        "07  RETURN COURSE EVIDENCE",
    ]
    colors = [(111, 198, 255), (198, 149, 255), (139, 233, 168)]
    for index, line in enumerate(code[: max(1, min(len(code), stage))]):
        image.text(70, 105 + index * 72, line, 5, colors[index % len(colors)])
    image.rect(920, 120, 260, 440, (28, 35, 46))
    image.text(955, 160, "BUDGET", 6, (255, 208, 115))
    image.text(955, 250, "4 / MIN", 6, (255, 255, 255))
    image.text(955, 340, "MAX 240", 6, (255, 255, 255))
    return image


def terminal_screen(success: bool) -> Canvas:
    image = Canvas(WIDTH, HEIGHT, (12, 18, 24))
    image.rect(0, 0, WIDTH, 62, (42, 50, 61))
    image.text(36, 17, "COURSE TERMINAL", 4, (220, 228, 238))
    image.text(52, 112, "DEV PROJECT TEST", 5, (137, 180, 250))
    if success:
        lines = ["TEST 01 PASS", "TEST 02 PASS", "BUILD SUCCESS", "DEV PROJECT READY"]
        color = (107, 219, 153)
    else:
        lines = ["TEST 01 PASS", "TEST 02 FAIL", "ERROR 500", "BUILD FAILED"]
        color = (249, 112, 102)
    for index, line in enumerate(lines):
        image.text(52, 205 + index * 86, line, 6, color)
    image.text(52, 610, "DEV PROJECT", 5, (229, 231, 235))
    return image


def scrolling_page() -> Canvas:
    image = Canvas(WIDTH, HEIGHT * 2, (255, 255, 255))
    image.rect(0, 0, WIDTH, 90, (18, 113, 91))
    image.text(54, 24, "COURSE NOTES", 7, (255, 255, 255))
    headings = ["TIMELINE COVERAGE", "FRAME QUALITY", "OCR EVIDENCE", "VLM BUDGET", "SAFE CLEANUP"]
    for index, heading in enumerate(headings):
        top = 150 + index * 245
        image.text(80, top, heading, 6, (18, 113, 91))
        for row in range(3):
            image.rect(84, top + 64 + row * 38, 1050 - row * 95, 12, (198, 207, 214))
    return image


def diagram_screen() -> Canvas:
    # A deliberately text-free diagram verifies that visually meaningful
    # evidence is not demoted merely because OCR returns little or nothing.
    image = Canvas(WIDTH, HEIGHT, (238, 244, 250))
    colors = [(45, 124, 198), (89, 177, 128), (230, 146, 57), (151, 92, 176)]
    for x in range(34, WIDTH - 34, 48):
        image.rect(x, 42, 4, HEIGHT - 84, (205, 216, 226))
    for y in range(42, HEIGHT - 42, 48):
        image.rect(34, y, WIDTH - 68, 4, (205, 216, 226))
    nodes = [(70, 112), (370, 112), (670, 112), (970, 112)]
    for index, (x, y) in enumerate(nodes):
        image.rect(x, y, 220, 150, (255, 255, 255))
        image.rect(x, y, 220, 18, colors[index])
        image.rect(x + 34, y + 55, 152, 18, colors[index])
        image.rect(x + 34, y + 92, 112, 18, colors[index])
        if index < len(nodes) - 1:
            image.rect(x + 220, y + 70, 80, 12, (72, 91, 112))
            image.rect(x + 282, y + 58, 18, 36, (72, 91, 112))
    image.rect(152, 390, 976, 16, (72, 91, 112))
    for index, height in enumerate((92, 164, 118, 230, 188, 276, 214, 310)):
        image.rect(190 + index * 108, 650 - height, 64, height, colors[index % len(colors)])
    for x in range(150, 1130, 54):
        image.rect(x, 648, 32, 8, (72, 91, 112))
    return image


def run(command: list[str]) -> None:
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()[-8:]
        raise RuntimeError("FFmpeg failed:\n" + "\n".join(message))


def encode_image(ffmpeg: str, image: Path, output: Path, duration: float, filter_value: str | None = None) -> None:
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(image)]
    if filter_value:
        command += ["-vf", filter_value]
    command += [
        "-t", str(duration), "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-g", str(FPS * 2), str(output),
    ]
    run(command)


def encode_black(ffmpeg: str, output: Path, duration: float) -> None:
    run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration}", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-g", str(FPS * 2), str(output),
    ])


def build(
    output: Path,
    ffmpeg: str,
    manifest: Path | None = None,
    target_duration_seconds: float | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lecturelens-synthetic-assets-") as temporary:
        work = Path(temporary)
        images = {
            "ppt": slide("ADAPTIVE VIDEO", ["FULL TIMELINE COVERAGE", "CLEAR COURSE EVIDENCE", "BOUNDED FRAME BUDGET"]),
            "transition": slide("SCENE TRANSITION", ["FADE BETWEEN SLIDES", "DO NOT KEEP BLUR", "SEARCH NEARBY FRAMES"], (158, 72, 128)),
            "scroll": scrolling_page(),
            "code-2": code_screen(2),
            "code-4": code_screen(4),
            "code-7": code_screen(7),
            "terminal-error": terminal_screen(False),
            "terminal-success": terminal_screen(True),
            "diagram": diagram_screen(),
            "final": slide("SUMMARY", ["SCAN LOW COST", "ANALYZE HIGH QUALITY", "PERSIST ONLY EVIDENCE"], (18, 113, 91)),
        }
        for name, image in images.items():
            image.save_png(work / f"{name}.png")

        segments: list[Path] = []
        scenarios: list[dict[str, float | str]] = []
        timeline_seconds = 0.0

        def segment(name: str, duration: float) -> Path:
            nonlocal timeline_seconds
            path = work / f"segment-{len(segments):02d}-{name}.mp4"
            segments.append(path)
            scenarios.append({
                "name": name,
                "start_seconds": timeline_seconds,
                "end_seconds": timeline_seconds + duration,
            })
            timeline_seconds += duration
            return path

        encode_image(ffmpeg, work / "ppt.png", segment("ppt-static", 8), 8)
        encode_image(ffmpeg, work / "transition.png", segment("ppt-transition", 3), 3, "boxblur=18:2")
        encode_black(ffmpeg, segment("black-screen", 3), 3)
        encode_image(
            ffmpeg,
            work / "scroll.png",
            segment("fast-scroll", 8),
            8,
            "crop=1280:720:0:'(in_h-out_h)*t/8',format=yuv420p",
        )
        encode_image(ffmpeg, work / "code-2.png", segment("code-progress-1", 12), 12)
        encode_image(ffmpeg, work / "code-4.png", segment("code-progress-2", 12), 12)
        encode_image(ffmpeg, work / "code-7.png", segment("code-progress-3", 14), 14)
        encode_image(ffmpeg, work / "terminal-error.png", segment("terminal-error", 15), 15)
        encode_image(ffmpeg, work / "terminal-success.png", segment("terminal-success", 15), 15)
        encode_image(ffmpeg, work / "code-7.png", segment("unchanged-code", 8), 8)
        encode_image(ffmpeg, work / "diagram.png", segment("visual-demo", 8), 8)
        encode_image(ffmpeg, work / "final.png", segment("long-static", 20), 20)

        concat_file = work / "concat.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
        video_only = work / "video-only.mp4"
        run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy", str(video_only),
        ])
        # A deterministic silent track exercises the real FFmpeg audio branch
        # while keeping ASR evaluation local and provider-independent.
        target_duration = target_duration_seconds if target_duration_seconds and target_duration_seconds > 0 else timeline_seconds
        base_output = output if target_duration <= timeline_seconds + 0.001 else work / "base-course.mp4"
        run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video_only),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
            "-map", "0:v:0", "-map", "1:a:0", "-t", f"{timeline_seconds:.3f}",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "32k", "-shortest",
            "-movflags", "+faststart", str(base_output),
        ])
        if base_output != output:
            run([
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-stream_loop", "-1", "-i", str(base_output), "-t", f"{target_duration:.3f}",
                "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart", str(output),
            ])
        if manifest is not None:
            base_scenarios = list(scenarios)
            if target_duration > timeline_seconds + 0.001:
                scenarios = []
                cycle = 0
                while cycle * timeline_seconds < target_duration:
                    offset = cycle * timeline_seconds
                    for scenario in base_scenarios:
                        start = offset + float(scenario["start_seconds"])
                        if start >= target_duration:
                            break
                        scenarios.append({
                            "name": f"{scenario['name']}-cycle-{cycle + 1}",
                            "start_seconds": start,
                            "end_seconds": min(target_duration, offset + float(scenario["end_seconds"])),
                        })
                    cycle += 1
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({
                    "schema_version": 1,
                    "video": str(output),
                    "duration_seconds": target_duration,
                    "scenarios": scenarios,
                }, indent=2) + "\n",
                encoding="utf-8",
            )


def parse_args() -> argparse.Namespace:
    default = Path(tempfile.gettempdir()) / f"lecturelens-synthetic-course-{int(time.time())}.mp4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default, help="Output MP4 (default: system temp directory)")
    parser.add_argument("--manifest", type=Path, help="Optional JSON scenario manifest for offline evaluation")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable")
    parser.add_argument(
        "--target-duration-seconds",
        type=float,
        help="Repeat the deterministic 126-second scenario cycle to this duration (for example 1200)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    executable = shutil.which(args.ffmpeg)
    if not executable:
        raise SystemExit(f"FFmpeg executable not found: {args.ffmpeg}")
    output = args.output.expanduser().resolve()
    manifest = args.manifest.expanduser().resolve() if args.manifest else None
    build(output, executable, manifest, args.target_duration_seconds)
    print(output)
    if manifest:
        print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
