#!/usr/bin/env python3
"""Offline, dependency-free comparison of three course-frame strategies.

The program invokes local FFmpeg/FFprobe (and Tesseract when available), measures
the produced files, writes JSON, and never calls a network or paid AI service.
It is an independent reproducible benchmark, not a Java profiler.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Frame:
    timestamp: float
    pixels: bytes
    width: int
    height: int
    mean: float
    variance: float
    sharpness: float
    edge_density: float
    black: bool
    blank: bool
    dhash: int
    path: Path


def command(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", "replace").splitlines()[-8:]
        raise RuntimeError("command failed: " + " ".join(args[:4]) + "\n" + "\n".join(tail))
    return result


def probe(ffprobe: str, video: Path) -> dict:
    raw = command([
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "format=duration:stream=width,height,avg_frame_rate,codec_name",
        "-of", "json", str(video),
    ]).stdout
    value = json.loads(raw)
    stream = value["streams"][0]
    numerator, denominator = stream.get("avg_frame_rate", "0/1").split("/", 1)
    return {
        "duration_seconds": float(value["format"]["duration"]),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": float(numerator) / max(1.0, float(denominator)),
        "codec": stream.get("codec_name"),
    }


def scan_changes(ffmpeg: str, video: Path, threshold: float) -> list[tuple[float, float]]:
    result = subprocess.run([
        ffmpeg, "-hide_banner", "-nostats", "-loglevel", "info", "-i", str(video), "-an", "-sn",
        "-vf", f"scale=480:-2,select='gt(scene,{threshold})',metadata=print", "-fps_mode", "vfr", "-f", "null",
        "NUL" if __import__("os").name == "nt" else "-",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-1200:])
    points: list[tuple[float, float]] = []
    timestamp: float | None = None
    for line in result.stderr.decode("utf-8", "replace").splitlines():
        timestamp_match = re.search(r"pts_time:([0-9]+(?:\.[0-9]+)?)", line)
        if timestamp_match:
            timestamp = float(timestamp_match.group(1))
            continue
        score_match = re.search(r"lavfi\.scene_score=([0-9]+(?:\.[0-9]+)?)", line)
        if timestamp is not None and score_match:
            points.append((timestamp, float(score_match.group(1))))
            timestamp = None
    return sorted(set(points))


def parse_pgm(data: bytes) -> tuple[int, int, bytes]:
    match = re.match(rb"P5\s+(?:#[^\r\n]*[\r\n]+\s*)*(\d+)\s+(\d+)\s+(\d+)\s", data)
    if not match or int(match.group(3)) != 255:
        raise RuntimeError("unexpected FFmpeg PGM output")
    width, height = int(match.group(1)), int(match.group(2))
    pixels = data[match.end() : match.end() + width * height]
    if len(pixels) != width * height:
        raise RuntimeError("truncated FFmpeg PGM output")
    return width, height, pixels


def laplacian_variance(pixels: bytes, width: int, height: int) -> float:
    values: list[int] = []
    step = max(1, min(width, height) // 180)
    for y in range(step, height - step, step):
        row = y * width
        for x in range(step, width - step, step):
            center = pixels[row + x]
            values.append(
                4 * center - pixels[row + x - step] - pixels[row + x + step]
                - pixels[(y - step) * width + x] - pixels[(y + step) * width + x]
            )
    return statistics.pvariance(values) if len(values) > 1 else 0.0


def dhash(pixels: bytes, width: int, height: int) -> int:
    # Compare small cell averages rather than one pixel.  Single-pixel sampling
    # aliases badly on sparse slide text and can call unrelated white slides equal.
    grid: list[list[float]] = []
    for y in range(8):
        row: list[float] = []
        y0, y1 = int(y * height / 8), max(int((y + 1) * height / 8), int(y * height / 8) + 1)
        for x in range(9):
            x0, x1 = int(x * width / 9), max(int((x + 1) * width / 9), int(x * width / 9) + 1)
            values = []
            for py in range(y0, y1, max(1, (y1 - y0) // 4)):
                for px in range(x0, x1, max(1, (x1 - x0) // 4)):
                    values.append(pixels[min(height - 1, py) * width + min(width - 1, px)])
            row.append(statistics.fmean(values))
        grid.append(row)
    result = 0
    for y in range(8):
        for x in range(8):
            result = (result << 1) | (grid[y][x] > grid[y][x + 1])
    return result


def edge_density(pixels: bytes, width: int, height: int) -> float:
    changed = 0
    compared = 0
    step = max(1, min(width, height) // 240)
    for y in range(0, height - step, step):
        row = y * width
        for x in range(0, width - step, step):
            value = pixels[row + x]
            changed += abs(value - pixels[row + x + step]) >= 24
            changed += abs(value - pixels[(y + step) * width + x]) >= 24
            compared += 2
    return changed / compared if compared else 0.0


def sample(
    ffmpeg: str, video: Path, timestamp: float, max_width: int, output: Path, image_format: str
) -> Frame:
    timestamp = max(0.0, timestamp)
    common = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}", "-i", str(video),
        "-map", "0:v:0", "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2",
    ]
    command(common + (["-q:v", "3"] if image_format == "jpg" else ["-compression_level", "3"]) + [str(output)])
    pgm = command(common + ["-f", "image2pipe", "-c:v", "pgm", "-"]).stdout
    width, height, pixels = parse_pgm(pgm)
    mean = statistics.fmean(pixels)
    variance = statistics.pvariance(pixels)
    return Frame(
        timestamp, pixels, width, height, mean, variance, laplacian_variance(pixels, width, height),
        edge_density(pixels, width, height),
        mean < 18.0, mean > 245.0 and variance < 8.0, dhash(pixels, width, height), output,
    )


def sample_batch(
    ffmpeg: str,
    video: Path,
    requests: list[tuple[float, Path]],
    max_width: int,
    batch_size: int = 12,
) -> tuple[list[Frame], dict[str, int]]:
    """Materialize PNG and grayscale analysis data with one FFmpeg process per bounded batch."""
    frames: list[Frame] = []
    process_count = 0
    failed = 0
    for start in range(0, len(requests), batch_size):
        batch = requests[start : start + batch_size]
        args = [ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "error"]
        normalized: list[tuple[float, Path, Path]] = []
        for request_index, (timestamp, output) in enumerate(batch):
            timestamp = max(0.0, timestamp)
            output.parent.mkdir(parents=True, exist_ok=True)
            pgm = output.with_suffix(f".{request_index}.pgm")
            normalized.append((timestamp, output, pgm))
            args += ["-ss", f"{timestamp:.3f}", "-i", str(video)]
        for input_index, (_, output, pgm) in enumerate(normalized):
            args += [
                "-map", f"{input_index}:v:0", "-frames:v", "1",
                "-vf", f"scale='min({max_width},iw)':-2", "-compression_level", "3", str(output),
                "-map", f"{input_index}:v:0", "-frames:v", "1",
                "-vf", f"scale='min({max_width},iw)':-2,format=gray", "-f", "image2", "-c:v", "pgm", str(pgm),
            ]
        process_count += 1
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False)
        if result.returncode != 0 and not any(output.is_file() for _, output, _ in normalized):
            tail = result.stderr.decode("utf-8", "replace").splitlines()[-8:]
            raise RuntimeError("batch sample failed\n" + "\n".join(tail))
        for timestamp, output, pgm in normalized:
            if not output.is_file() or not pgm.is_file():
                failed += 1
                output.unlink(missing_ok=True)
                pgm.unlink(missing_ok=True)
                continue
            width, height, pixels = parse_pgm(pgm.read_bytes())
            pgm.unlink(missing_ok=True)
            mean = statistics.fmean(pixels)
            variance = statistics.pvariance(pixels)
            frames.append(Frame(
                timestamp, pixels, width, height, mean, variance,
                laplacian_variance(pixels, width, height), edge_density(pixels, width, height),
                mean < 18.0, mean > 245.0 and variance < 8.0,
                dhash(pixels, width, height), output,
            ))
    return frames, {
        "sample_batches": process_count,
        "ffmpeg_process_count": process_count,
        "sample_requests": len(requests),
        "sample_succeeded": len(frames),
        "sample_failed": failed,
    }


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def hamming(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def plan_candidates(duration: float, changes: Iterable[tuple[float, float]]) -> list[tuple[float, str, float]]:
    # Stay safely before the final frame boundary; container duration can be one
    # frame longer than the last decodable presentation timestamp.
    end = max(0.0, duration - 0.25)
    values = [(0.0, "START", 1.0), (end, "END", 1.0)]
    values += [
        (min(end, max(0.0, timestamp)), "SCENE_CHANGE" if score >= 0.30 else "CONTENT_CHANGE", score)
        for timestamp, score in changes
    ]
    interval = 30.0 if duration <= 3600 else 45.0 if duration <= 7200 else 60.0
    value = interval
    while value < end:
        values.append((value, "PERIODIC_ANCHOR", 0.5))
        value += interval
    window_count = max(1, math.ceil(duration / 60.0))
    for window in range(window_count):
        start, stop = window * 60.0, min(end, (window + 1) * 60.0)
        values.append((start + max(0.0, stop - start) / 2.0, "WINDOW_COVERAGE", 0.2))
    priority = {
        "START": 5, "END": 5, "SCENE_CHANGE": 5, "CONTENT_CHANGE": 4,
        "PERIODIC_ANCHOR": 3, "WINDOW_COVERAGE": 2,
    }
    merged: list[tuple[float, str, float]] = []
    for item in sorted(values, key=lambda row: row[0]):
        if merged and item[0] - merged[-1][0] <= 1.0:
            if (priority[item[1]], item[2]) > (priority[merged[-1][1]], merged[-1][2]):
                merged[-1] = item
        else:
            merged.append(item)
    windows: dict[int, list[tuple[float, str, float]]] = {}
    for item in merged:
        windows.setdefault(int(item[0] // 60), []).append(item)
    bounded: list[tuple[float, str, float]] = []
    for window, items in windows.items():
        if len(items) <= 6:
            bounded += items
            continue
        buckets: dict[int, list[tuple[float, str, float]]] = {}
        for item in items:
            bucket = min(5, max(0, int((item[0] - window * 60.0) // 10.0)))
            buckets.setdefault(bucket, []).append(item)
        for bucket, values_in_bucket in buckets.items():
            target = window * 60.0 + (bucket + 0.5) * 10.0
            bounded.append(min(values_in_bucket, key=lambda row: (
                -priority[row[1]], abs(row[0] - target), -row[2], row[0]
            )))
    return sorted(bounded)


def bound_adaptive_candidates(
    planned: list[tuple[float, str, float]], duration: float
) -> list[tuple[float, str, float]]:
    """Mirror R1's fair global persistence budget before costly sampling."""
    limit = 240
    priority = {
        "SCENE_CHANGE": 5, "CONTENT_CHANGE": 4, "START": 4, "END": 4,
        "PERIODIC_ANCHOR": 3, "WINDOW_COVERAGE": 2,
    }
    windows: dict[int, list[tuple[float, str, float]]] = {}
    for item in planned:
        windows.setdefault(int(item[0] // 60), []).append(item)
    groups = [sorted(items, key=lambda row: (-priority[row[1]], -row[2], row[0])) for items in windows.values()]
    selected: list[tuple[float, str, float]] = []
    round_index = 0
    while len(selected) < limit:
        eligible = [items for items in groups if len(items) > round_index]
        if not eligible:
            break
        slots = min(limit - len(selected), len(eligible))
        if slots == len(eligible):
            selected.extend(items[round_index] for items in eligible)
        elif slots == 1:
            selected.append(eligible[len(eligible) // 2][round_index])
        else:
            for index in range(slots):
                position = round(index * (len(eligible) - 1) / (slots - 1))
                selected.append(eligible[position][round_index])
        round_index += 1
    return sorted(selected)


CONTENT_BUDGETS = {
    "SLIDE": 2,
    "CODE_OR_TERMINAL": 4,
    "VISUAL_DEMO": 3,
    "TALKING_OR_LOW_INFORMATION": 1,
    "UNKNOWN": 2,
}

VLM_BUDGETS = {
    "SLIDE": 1,
    "CODE_OR_TERMINAL": 2,
    "VISUAL_DEMO": 2,
    "TALKING_OR_LOW_INFORMATION": 1,
    "UNKNOWN": 1,
}

CONTENT_IMPORTANCE = {
    "CODE_OR_TERMINAL": 0,
    "VISUAL_DEMO": 1,
    "SLIDE": 2,
    "UNKNOWN": 3,
    "TALKING_OR_LOW_INFORMATION": 4,
}

REPRESENTATIVE_TYPES = ("CODE_OR_TERMINAL", "VISUAL_DEMO", "SLIDE")
CONTENT_VALUE_BONUS = {
    "CODE_OR_TERMINAL": 1.5,
    "VISUAL_DEMO": 2.0,
    "SLIDE": 1.0,
    "UNKNOWN": 0.25,
    "TALKING_OR_LOW_INFORMATION": 0.0,
}


def classify_content(frame: Frame) -> str:
    if frame.mean < 125 and frame.edge_density >= 0.008:
        return "CODE_OR_TERMINAL"
    if frame.edge_density >= 0.045 and frame.variance >= 500:
        return "VISUAL_DEMO"
    if frame.mean >= 175 and frame.edge_density >= 0.008:
        return "SLIDE"
    if frame.edge_density < 0.006:
        return "TALKING_OR_LOW_INFORMATION"
    return "UNKNOWN"


def fair_content_limit(frames: list[Frame], budgets: dict[str, int], maximum: int) -> list[Frame]:
    """Mirror the production temporal/type representative allocator.

    Quality filtering remains authoritative: representative retention never
    revives black, blank, blurred, or already-deduplicated samples.
    """
    frames = [
        frame for frame in frames
        if not frame.black and not frame.blank and frame.sharpness >= 80.0
    ]
    if not frames or maximum <= 0:
        return []
    windows: dict[int, list[Frame]] = {}
    for frame in sorted(frames, key=lambda item: item.timestamp):
        windows.setdefault(int(frame.timestamp // 60), []).append(frame)
    per_window_budget: dict[int, int] = {}
    for window, values in windows.items():
        dominant = min((classify_content(value) for value in values), key=CONTENT_IMPORTANCE.get)
        per_window_budget[window] = min(4, budgets[dominant])
        budget = per_window_budget[window]
        if len(values) > budget:
            buckets: dict[int, list[Frame]] = {}
            for value in values:
                bucket = min(budget - 1, max(0, int((value.timestamp - window * 60.0) // (60.0 / budget))))
                buckets.setdefault(bucket, []).append(value)
            covered = [max(bucket, key=frame_priority) for bucket in buckets.values()]
            for content_type in REPRESENTATIVE_TYPES:
                candidates = [value for value in values if classify_content(value) == content_type]
                if not candidates or any(classify_content(value) == content_type for value in covered):
                    continue
                representative = max(candidates, key=frame_priority)
                if len(covered) < budget:
                    covered.append(representative)
                    continue
                counts = {
                    name: sum(classify_content(value) == name for value in covered)
                    for name in REPRESENTATIVE_TYPES
                }
                replaceable = [
                    value for value in covered
                    if classify_content(value) not in REPRESENTATIVE_TYPES
                    or counts[classify_content(value)] > 1
                ]
                if replaceable:
                    covered.remove(min(replaceable, key=frame_priority))
                    covered.append(representative)
            if len(covered) < budget:
                covered += sorted(
                    (value for value in values if value not in covered), key=frame_priority, reverse=True
                )[: budget - len(covered)]
            windows[window] = covered
        windows[window].sort(key=lambda value: (-frame_priority(value), value.timestamp))

    window_ids = list(windows)
    if len(window_ids) <= maximum:
        covered_windows = window_ids
    elif maximum == 1:
        covered_windows = [window_ids[len(window_ids) // 2]]
    else:
        covered_windows = [
            window_ids[round(index * (len(window_ids) - 1) / (maximum - 1))]
            for index in range(maximum)
        ]
    selected: list[Frame] = [windows[window][0] for window in covered_windows]

    for content_type in REPRESENTATIVE_TYPES:
        if any(classify_content(frame) == content_type for frame in selected):
            continue
        candidates = [frame for frame in frames if classify_content(frame) == content_type and frame not in selected]
        if not candidates:
            continue
        representative = max(candidates, key=frame_priority)
        target_window = int(representative.timestamp // 60)
        target_count = sum(int(frame.timestamp // 60) == target_window for frame in selected)
        if len(selected) < maximum and target_count < per_window_budget[target_window]:
            selected.append(representative)
            continue
        type_counts = {
            name: sum(classify_content(frame) == name for frame in selected)
            for name in REPRESENTATIVE_TYPES
        }
        window_counts = {
            window: sum(int(frame.timestamp // 60) == window for frame in selected)
            for window in windows
        }
        target_full = target_count >= per_window_budget[target_window]
        replaceable = [
            frame for frame in selected
            if (not target_full or int(frame.timestamp // 60) == target_window)
            and (
                classify_content(frame) not in REPRESENTATIVE_TYPES
                or type_counts[classify_content(frame)] > 1
            )
            and (
                int(frame.timestamp // 60) == target_window
                or window_counts[int(frame.timestamp // 60)] > 1
            )
        ]
        if replaceable:
            selected.remove(min(replaceable, key=frame_priority))
            selected.append(representative)

    round_index = 0
    while len(selected) < maximum:
        found = False
        for window, values in windows.items():
            if sum(int(frame.timestamp // 60) == window for frame in selected) >= per_window_budget[window]:
                continue
            candidate = next((value for value in values[round_index:] if value not in selected), None)
            if candidate is None:
                candidate = next((value for value in values if value not in selected), None)
            if candidate is not None:
                selected.append(candidate)
                found = True
                if len(selected) == maximum:
                    break
        if not found:
            break
        round_index += 1
    return sorted(selected, key=lambda item: item.timestamp)


def quality_score(frame: Frame) -> float:
    return math.log1p(frame.sharpness) + min(frame.variance, 5000) / 1800 - abs(frame.mean - 145) / 100


def frame_priority(frame: Frame) -> float:
    return quality_score(frame) + CONTENT_VALUE_BONUS[classify_content(frame)]


def pre_ocr_limit(
    prepared: list[tuple[Frame, str]], maximum: int = 360
) -> tuple[list[tuple[Frame, str]], list[tuple[Frame, str]], list[tuple[Frame, str]]]:
    windows: dict[int, list[tuple[Frame, str]]] = {}
    for item in sorted(prepared, key=lambda value: value[0].timestamp):
        windows.setdefault(int(item[0].timestamp // 60), []).append(item)
    visual_only: list[tuple[Frame, str]] = []
    ocr_windows: dict[int, list[tuple[Frame, str]]] = {}
    limits: dict[int, int] = {}
    source_rank = {
        "CONTENT_CHANGE": 6, "SCENE_CHANGE": 5, "START": 4, "END": 4,
        "PERIODIC_ANCHOR": 3, "WINDOW_COVERAGE": 2,
    }
    for window, values in windows.items():
        values.sort(key=lambda item: (-source_rank[item[1]], -frame_priority(item[0]), item[0].timestamp))
        visual = next((item for item in values if (
            item[1] == "SCENE_CHANGE" and item[0].edge_density >= 0.07 and item[0].variance >= 120
        )), None)
        if visual is not None:
            visual_only.append(visual)
        remaining = [item for item in values if item is not visual]
        if not remaining:
            continue
        ocr_windows[window] = remaining
        dense = sum(source == "CONTENT_CHANGE" for _, source in remaining) >= 2
        low_information = all(
            frame.edge_density < 0.012 and source in {"PERIODIC_ANCHOR", "WINDOW_COVERAGE"}
            for frame, source in remaining
        )
        limits[window] = min(len(remaining), 1 if low_information else 4 if dense else 2)

    selected: list[tuple[Frame, str]] = []
    round_index = 0
    while len(selected) < maximum:
        eligible = [
            (window, values) for window, values in ocr_windows.items()
            if round_index < limits[window] and round_index < len(values)
        ]
        if not eligible:
            break
        slots = min(maximum - len(selected), len(eligible))
        if round_index:
            eligible.sort(key=lambda item: (
                not any(source == "CONTENT_CHANGE" for _, source in item[1]), item[0]
            ))
        if slots == len(eligible):
            chosen = eligible
        elif slots == 1:
            chosen = [eligible[len(eligible) // 2]]
        else:
            chosen = [eligible[round(index * (len(eligible) - 1) / (slots - 1))] for index in range(slots)]
        selected += [values[round_index] for _, values in chosen]
        round_index += 1
    retained_ids = {id(item[0]) for item in selected + visual_only}
    rejected = [item for item in prepared if id(item[0]) not in retained_ids]
    return (
        sorted(selected, key=lambda item: item[0].timestamp),
        sorted(visual_only, key=lambda item: item[0].timestamp),
        rejected,
    )


def coverage(timestamps: list[float], duration: float) -> dict:
    if not timestamps or duration <= 0:
        return {"timeline_span_ratio": 0.0, "window_coverage_ratio": 0.0, "max_gap_seconds": None}
    ordered = sorted(timestamps)
    window_count = max(1, math.ceil(duration / 60))
    windows = {min(window_count - 1, int(value // 60)) for value in ordered}
    gaps = [ordered[0], duration - ordered[-1]] + [b - a for a, b in zip(ordered, ordered[1:])]
    return {
        "timeline_span_ratio": round(max(0.0, ordered[-1] - ordered[0]) / duration, 6),
        "window_coverage_ratio": round(len(windows) / window_count, 6),
        "max_gap_seconds": round(max(gaps), 3),
        "first_timestamp_seconds": round(ordered[0], 3),
        "last_timestamp_seconds": round(ordered[-1], 3),
    }


def persist(ffmpeg: str, video: Path, frames: list[Frame], directory: Path) -> int:
    total = 0
    target = directory / "persisted"
    target.mkdir()
    for index, frame in enumerate(frames):
        output = target / f"evidence-{index:04d}.jpg"
        common = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{frame.timestamp:.3f}", "-i", str(video),
            "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", "4", str(output),
        ]
        command(common)
        total += output.stat().st_size
    return total


def ocr_metrics(tesseract: str | None, frames: list[Frame]) -> dict:
    if not tesseract:
        return {
            "available": False, "planned_frame_count": len(frames), "attempted_frame_count": 0,
            "succeeded_frame_count": 0, "empty_frame_count": 0, "failed_frame_count": 0,
            "valid_frame_count": None,
        }
    valid = 0
    succeeded = 0
    empty = 0
    failed = 0
    attempted = 0
    for frame in frames:
        attempted += 1
        try:
            result = subprocess.run(
                [tesseract, str(frame.path), "stdout", "-l", "eng", "--oem", "1", "--psm", "6"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
            )
            if result.returncode != 0:
                failed += 1
                continue
            text = result.stdout.decode("utf-8", "replace")
            if re.search(r"[A-Za-z0-9]", text):
                succeeded += 1
            else:
                empty += 1
            if len(re.sub(r"[^A-Za-z0-9]", "", text)) >= 8:
                valid += 1
        except (subprocess.TimeoutExpired, OSError):
            failed += 1
    return {
        "available": True, "planned_frame_count": len(frames), "attempted_frame_count": attempted,
        "succeeded_frame_count": succeeded, "empty_frame_count": empty,
        "failed_frame_count": failed, "valid_frame_count": valid,
    }


def summarize(
    name: str, candidate_timestamps: list[float], samples: list[Frame], final: list[Frame], duplicate_count: int,
    duration: float, elapsed: float, peak: int, persisted_bytes: int, tesseract: str | None,
    *, ocr_frames: list[Frame] | None = None, runtime_metrics: dict[str, int] | None = None,
    stable_frame_count: int | None = None, pre_ocr_rejected_count: int = 0,
    ocr_result: dict | None = None,
) -> dict:
    content_types = {name: sum(classify_content(frame) == name for frame in final) for name in CONTENT_BUDGETS}
    vlm_frames = fair_content_limit(final, VLM_BUDGETS, 80)
    runtime = runtime_metrics or {
        "sample_batches": len(samples), "ffmpeg_process_count": len(samples) * 2,
        "sample_requests": len(samples), "sample_succeeded": len(samples), "sample_failed": 0,
    }
    ocr = ocr_result or ocr_metrics(tesseract, final if ocr_frames is None else ocr_frames)
    return {
        "strategy": name,
        "candidate_timestamp_count": len(candidate_timestamps),
        "extracted_sample_count": len(samples),
        "final_frame_count": len(final),
        "final_timestamps_seconds": [round(frame.timestamp, 3) for frame in final],
        "blurred_sample_count": sum(frame.sharpness < 80.0 for frame in samples),
        "black_sample_count": sum(frame.black for frame in samples),
        "duplicate_rejected_or_observed_count": duplicate_count,
        **runtime,
        "stable_frame_count": len(final) if stable_frame_count is None else stable_frame_count,
        "pre_ocr_rejected_count": pre_ocr_rejected_count,
        "final_keyframe_count": len(final),
        "content_type_counts": content_types,
        "time_coverage": {
            "candidates": coverage(candidate_timestamps, duration),
            "final_frames": coverage([frame.timestamp for frame in final], duration),
        },
        "ocr": ocr,
        "vlm_plan": {
            "network_calls_made": 0,
            "planned_frame_count": len(vlm_frames),
            "planned_timestamps_seconds": [round(frame.timestamp, 3) for frame in vlm_frames],
            "global_max_frames_per_minute": 4,
            "content_budgets_per_minute": VLM_BUDGETS,
            "max_frames_total": 80,
        },
        "elapsed_seconds": round(elapsed, 3),
        "ffmpeg_processes_per_minute": round(runtime["ffmpeg_process_count"] / max(duration / 60.0, 1e-9), 3),
        "ocr_calls_per_minute": round(ocr["attempted_frame_count"] / max(duration / 60.0, 1e-9), 3),
        "temp_peak_bytes_approx": peak,
        "persisted_bytes": persisted_bytes,
    }


def legacy(ffmpeg: str, video: Path, duration: float, root: Path, tesseract: str | None) -> dict:
    started = time.perf_counter()
    directory = root / "legacy"
    directory.mkdir()
    timestamps = [float(value) for value in range(min(3000, math.ceil(duration)))]
    frames = [sample(ffmpeg, video, value, 320, directory / f"candidate-{index:04d}.jpg", "jpg") for index, value in enumerate(timestamps)]
    final: list[Frame] = []
    last_selected = -1e12
    last_anchor = -1e12
    per_minute: dict[int, int] = {}
    duplicate_observed = 0
    for index, frame in enumerate(frames):
        if index and hamming(frames[index - 1].dhash, frame.dhash) <= 5:
            duplicate_observed += 1
        changed_ratio = 0.0
        average_delta = 0.0
        if index:
            deltas = [abs(a - b) for a, b in zip(frames[index - 1].pixels, frame.pixels)]
            changed_ratio = sum(delta >= 18 for delta in deltas) / len(deltas)
            average_delta = statistics.fmean(deltas)
        reason = not final or frame.timestamp - last_anchor >= 60 or changed_ratio >= 0.08 or average_delta >= 18
        minute = int(frame.timestamp // 60)
        if reason and frame.timestamp - last_selected >= 3 and per_minute.get(minute, 0) < 4 and len(final) < 300:
            final.append(frame)
            per_minute[minute] = per_minute.get(minute, 0) + 1
            last_selected = frame.timestamp
            if len(final) == 1 or frame.timestamp - last_anchor >= 60:
                last_anchor = frame.timestamp
    peak = directory_size(directory)
    persisted_bytes = persist(ffmpeg, video, final, directory)
    peak = max(peak, directory_size(directory))
    return summarize("legacy", timestamps, frames, final, duplicate_observed, duration, time.perf_counter() - started, peak, persisted_bytes, tesseract)


def scene_anchor(
    ffmpeg: str, video: Path, duration: float, planned: list[tuple[float, str, float]], root: Path, tesseract: str | None
) -> dict:
    started = time.perf_counter()
    directory = root / "scene-anchor"
    directory.mkdir()
    frames = [sample(ffmpeg, video, item[0], 1600, directory / f"candidate-{index:04d}.png", "png") for index, item in enumerate(planned)]
    final: list[Frame] = []
    duplicates = 0
    for frame in frames:
        if frame.black or frame.blank or frame.sharpness < 80:
            continue
        if any(abs(frame.timestamp - old.timestamp) <= 120 and hamming(frame.dhash, old.dhash) <= 5 for old in final):
            duplicates += 1
            continue
        final.append(frame)
    persisted_bytes = persist(ffmpeg, video, final, directory)
    peak = directory_size(directory)
    return summarize("scene-anchor", [item[0] for item in planned], frames, final, duplicates, duration, time.perf_counter() - started, peak, persisted_bytes, tesseract)


def adaptive(
    ffmpeg: str, video: Path, duration: float, planned: list[tuple[float, str, float]], root: Path, tesseract: str | None
) -> dict:
    started = time.perf_counter()
    directory = root / "adaptive"
    directory.mkdir()
    bounded = bound_adaptive_candidates(planned, duration)
    requests: list[tuple[float, Path]] = []
    outputs_by_candidate: list[list[Path]] = []
    for index, item in enumerate(bounded):
        candidate_outputs: list[Path] = []
        timestamps: list[float] = []
        for offset_index, offset in enumerate((-0.2, 0.4, 0.9, 1.4)):
            timestamp = min(max(0.0, item[0] + offset), max(0.0, duration - 0.25))
            if any(abs(timestamp - old) < 0.001 for old in timestamps):
                continue
            timestamps.append(timestamp)
            output = directory / f"candidate-{index:04d}-{offset_index}.png"
            candidate_outputs.append(output)
            requests.append((timestamp, output))
        outputs_by_candidate.append(candidate_outputs)
    samples, runtime_metrics = sample_batch(ffmpeg, video, requests, 1600, 12)
    peak = directory_size(directory)
    by_output = {frame.path: frame for frame in samples}
    prepared: list[tuple[Frame, str]] = []
    for index, item in enumerate(bounded):
        nearby = [by_output[path] for path in outputs_by_candidate[index] if path in by_output]
        strict = [frame for frame in nearby if not frame.black and not frame.blank and frame.sharpness >= 80]
        relaxed = [frame for frame in nearby if not frame.black and not frame.blank]
        eligible = strict or (relaxed if item[1] in {"START", "END", "PERIODIC_ANCHOR"} else [])
        if item[1] in {"SCENE_CHANGE", "CONTENT_CHANGE"}:
            eligible = [frame for frame in eligible if frame.timestamp >= item[0]]
        if eligible:
            retained = max(eligible, key=lambda frame: (
                quality_score(frame),
                frame.timestamp >= item[0] if item[1] in {"SCENE_CHANGE", "CONTENT_CHANGE"} else True,
                -abs(frame.timestamp - item[0]),
            ))
            prepared.append((retained, item[1]))
            for frame in nearby:
                if frame is not retained:
                    frame.path.unlink(missing_ok=True)
        else:
            for frame in nearby:
                frame.path.unlink(missing_ok=True)
    distinct: list[tuple[Frame, str]] = []
    duplicates = 0
    for frame, source in prepared:
        exact_repeat = any(
            abs(frame.timestamp - old.timestamp) <= 120 and hamming(frame.dhash, old.dhash) == 0
            for old, _ in distinct
        )
        near_repeat_in_window = any(
            int(frame.timestamp // 60) == int(old.timestamp // 60)
            and hamming(frame.dhash, old.dhash) <= 5
            for old, _ in distinct
        )
        protected_change = source in {"SCENE_CHANGE", "CONTENT_CHANGE"} and all(
            abs(frame.timestamp - old.timestamp) >= 3 for old, _ in distinct
        )
        if (exact_repeat and not protected_change) or (
            near_repeat_in_window and source not in {"SCENE_CHANGE", "CONTENT_CHANGE"}
        ):
            duplicates += 1
            frame.path.unlink(missing_ok=True)
        else:
            distinct.append((frame, source))
    ocr_prepared, visual_only, pre_ocr_rejected = pre_ocr_limit(distinct, 360)
    for frame, _ in pre_ocr_rejected:
        frame.path.unlink(missing_ok=True)
    ocr_frames = [frame for frame, _ in ocr_prepared]
    ocr_result = ocr_metrics(tesseract, ocr_frames)
    retained = [frame for frame, _ in ocr_prepared + visual_only]
    final = fair_content_limit(retained, CONTENT_BUDGETS, 240)
    final_ids = {id(frame) for frame in final}
    for frame in retained:
        if id(frame) not in final_ids:
            frame.path.unlink(missing_ok=True)
    persisted_bytes = persist(ffmpeg, video, final, directory)
    peak = max(peak, directory_size(directory))
    return summarize(
        "adaptive", [item[0] for item in planned], samples, final, duplicates, duration,
        time.perf_counter() - started, peak, persisted_bytes, tesseract,
        ocr_frames=ocr_frames, runtime_metrics=runtime_metrics,
        stable_frame_count=len(prepared), pre_ocr_rejected_count=len(pre_ocr_rejected),
        ocr_result=ocr_result,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()) / "lecturelens-vision-evaluation.json")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--keep-workdir", action="store_true", help="Keep sampled media for debugging (default: delete)")
    parser.add_argument("--scenario-manifest", type=Path, help="Optional synthetic scenario manifest")
    parser.add_argument(
        "--adaptive-only",
        action="store_true",
        help="Run only the optimized strategy; original costs remain a theoretical model (recommended for long media)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video = args.video.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"video not found: {video}")
    ffmpeg, ffprobe = shutil.which(args.ffmpeg), shutil.which(args.ffprobe)
    if not ffmpeg or not ffprobe:
        raise SystemExit("FFmpeg and FFprobe must both be available")
    metadata = probe(ffprobe, video)
    changes = scan_changes(ffmpeg, video, 0.005)
    strong_scenes = [point for point in changes if point[1] >= 0.30]
    scene_planned = plan_candidates(metadata["duration_seconds"], strong_scenes)
    adaptive_planned = plan_candidates(metadata["duration_seconds"], changes)
    temporary = Path(tempfile.mkdtemp(prefix="lecturelens-vision-eval-"))
    tesseract = shutil.which("tesseract")
    try:
        optimized = adaptive(ffmpeg, video, metadata["duration_seconds"], adaptive_planned, temporary, tesseract)
        strategies = [optimized] if args.adaptive_only else [
            legacy(ffmpeg, video, metadata["duration_seconds"], temporary, tesseract),
            scene_anchor(ffmpeg, video, metadata["duration_seconds"], scene_planned, temporary, tesseract),
            optimized,
        ]
        if args.scenario_manifest:
            manifest = json.loads(args.scenario_manifest.expanduser().resolve().read_text(encoding="utf-8"))
            for strategy in strategies:
                final_timestamps = strategy.get("final_timestamps_seconds", [])
                selected = strategy.get("vlm_plan", {}).get("planned_timestamps_seconds", [])
                strategy["synthetic_scenario_coverage"] = [
                    {
                        **scenario,
                        "final_frame_count": sum(
                            scenario["start_seconds"] <= value < scenario["end_seconds"]
                            for value in final_timestamps
                        ),
                        "vlm_planned_count": sum(
                            scenario["start_seconds"] <= value < scenario["end_seconds"] for value in selected
                        ),
                    }
                    for scenario in manifest.get("scenarios", [])
                ]
        report = {
            "schema_version": 1,
            "measurement_scope": "independent offline strategy reproduction; no network or VLM calls",
            "source": {
                "path": str(video), **metadata,
                "scene_change_count": len(strong_scenes),
                "subtle_content_change_count": len(changes) - len(strong_scenes),
            },
            "thresholds": {
                "scene": 0.30, "content_change": 0.005, "sharpness": 80.0,
                "black_mean": 18.0, "dhash_distance": 5,
            },
            "ocr_availability": {"tesseract": bool(tesseract), "executable": tesseract},
            "resource_model": {
                "original_theoretical": {
                    "planned_candidates": len(adaptive_planned),
                    "neighbor_samples_per_candidate": 4,
                    "ffmpeg_process_count": len(adaptive_planned) * 4,
                    "ocr_call_count": len(adaptive_planned),
                },
                "optimized_actual": {
                    "sample_batches": strategies[-1]["sample_batches"],
                    "ffmpeg_process_count": strategies[-1]["ffmpeg_process_count"],
                    "sample_requests": strategies[-1]["sample_requests"],
                    "sample_succeeded": strategies[-1]["sample_succeeded"],
                    "sample_failed": strategies[-1]["sample_failed"],
                    "ocr_call_count": strategies[-1]["ocr"]["attempted_frame_count"],
                    "ffmpeg_processes_per_minute": strategies[-1]["ffmpeg_processes_per_minute"],
                    "ocr_calls_per_minute": strategies[-1]["ocr_calls_per_minute"],
                    "time_coverage": strategies[-1]["time_coverage"]["final_frames"],
                    "temp_peak_bytes_approx": strategies[-1]["temp_peak_bytes_approx"],
                },
            },
            "temp_peak_note": "Approximation from actual files in the strategy workspace; excludes OS/process buffers and PGM pipes.",
            "strategies": strategies,
        }
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output)
    finally:
        if args.keep_workdir:
            print(f"workdir={temporary}")
        else:
            shutil.rmtree(temporary, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
