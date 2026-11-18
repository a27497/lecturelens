"""Gold citation check against the caption windows the auditors read.

Captions are stored as ~30 s windows, one per line: "[mm:ss-mm:ss] text". A gold cue
{start, end, quote} is valid only when start is a window's start label, end is a window's end
label at or after it, the quote occurs in the text of exactly those windows, and the range is
minimal: dropping the first or the last window would lose the quote. So a quote that runs across
a window boundary must name both windows, and a cue cannot drift one window off its quote.

Matching ignores case, punctuation and whitespace runs (caption line breaks and "--" vary); the
words and their order must match.
"""

import re
from pathlib import Path

WINDOW = re.compile(r"^\[(\d+:\d\d)-(\d+:\d\d)\] (.*)$")


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def parse_windows(text):
    windows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = WINDOW.match(line)
        if not match:
            raise ValueError(f"caption line {number} is not a window")
        windows.append(match.groups())
    return windows


def load_windows(path):
    return parse_windows(Path(path).read_text())


def _contains(windows, first, last, quote):
    return quote in norm(" ".join(w[2] for w in windows[first : last + 1]))


def check_cue(cue, windows):
    """Return None if the cue is valid, else a short reason."""
    quote = norm(cue["quote"])
    if not quote:
        return "empty quote"
    starts = [i for i, w in enumerate(windows) if w[0] == cue["start"]]
    if not starts:
        return f"start {cue['start']} is not a window start"
    first = starts[0]
    ends = [i for i, w in enumerate(windows) if w[1] == cue["end"] and i >= first]
    if not ends:
        return f"end {cue['end']} is not a window end at or after {cue['start']}"
    last = ends[0]
    if not _contains(windows, first, last, quote):
        return "quote not in the cited windows"
    if last > first and (
        _contains(windows, first + 1, last, quote) or _contains(windows, first, last - 1, quote)
    ):
        return "cue wider than the quote"
    return None


def locate(quote, windows, max_span=3):
    """Minimal window ranges (start label, end label) that contain the quote, for repair hints."""
    quote = norm(quote)
    found = []
    for first in range(len(windows)):
        for last in range(first, min(first + max_span, len(windows))):
            if _contains(windows, first, last, quote):
                cue = {"start": windows[first][0], "end": windows[last][1], "quote": quote}
                if check_cue(cue, windows) is None:
                    found.append((windows[first][0], windows[last][1]))
                break
    return found


def check_items(items, windows_by_lecture):
    """Errors for every answerable item's cues; should-abstain items carry no cues."""
    errors = []
    for item in items:
        windows = windows_by_lecture[item["lecture_id"]]
        for p, point in enumerate(item.get("key_points") or [], 1):
            if not point["cues"]:
                errors.append(f"{item['item_id']} kp{p}: key point without cue")
            for c, cue in enumerate(point["cues"], 1):
                reason = check_cue(cue, windows)
                if reason:
                    errors.append(f"{item['item_id']} kp{p} cue{c} {cue['start']}-{cue['end']}: {reason}")
    return errors
