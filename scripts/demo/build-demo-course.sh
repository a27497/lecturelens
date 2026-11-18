#!/usr/bin/env bash
# Rebuilds fixtures/demo/binary-search-demo.mp4 from the self-written subtitle file.
# The committed MP4 is the source of truth for the demo stack; this script documents
# how it was produced and needs FFmpeg with libx264 and the DejaVu Sans font.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture_dir="$repo_root/fixtures/demo"
vtt="$fixture_dir/binary-search.en.vtt"
output="$fixture_dir/binary-search-demo.mp4"
font="${DEMO_FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf}"
mono="${DEMO_MONO_FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf}"

command -v ffmpeg >/dev/null 2>&1 || { printf 'FAIL ffmpeg missing\n' >&2; exit 1; }
[[ -f "$font" && -f "$mono" ]] || { printf 'FAIL font missing: set DEMO_FONT / DEMO_MONO_FONT\n' >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Each slide: start end title line1 line2 line3 (seconds match the subtitle sections).
slides=(
  "0|16|Binary search|Synthetic demo lecture|Input: an array sorted in ascending order|"
  "16|64|The loop|low, high = 0, n - 1|mid = low + (high - low) / 2|stop when low > high (not found)"
  "64|96|Worked example|[3, 8, 15, 21, 34, 42, 57], target 34|mid 3 -> 21 < 34;  mid 5 -> 42 > 34|mid 4 -> 34: three comparisons, return 4"
  "96|120|Cost|each step halves the range: O(log n)|n = 1,000,000 -> about 20 comparisons|linear scan: O(n)"
  "120|152|Pitfalls|(low + high) / 2 can overflow|low = mid (not mid + 1) can loop forever|unsorted input -> wrong answer"
)

filters="drawbox=x=40:y=36:w=560:h=288:color=0xffffff:t=fill,drawbox=x=40:y=36:w=8:h=288:color=0x2f7d65:t=fill"
filters+=",drawtext=fontfile=$font:text='LectureLens demo course (synthetic)':x=64:y=300:fontsize=12:fontcolor=0x7a8580"
index=0
for slide in "${slides[@]}"; do
  IFS='|' read -r start end title l1 l2 l3 <<<"$slide"
  enable="between(t\\,$start\\,$end)"
  for part in title l1 l2 l3; do
    printf '%s' "${!part}" >"$work/$index-$part.txt"
  done
  filters+=",drawtext=fontfile=$font:textfile=$work/$index-title.txt:x=64:y=64:fontsize=30:fontcolor=0x202a26:enable='$enable'"
  filters+=",drawtext=fontfile=$mono:textfile=$work/$index-l1.txt:x=64:y=132:fontsize=16:fontcolor=0x2f7d65:enable='$enable'"
  filters+=",drawtext=fontfile=$mono:textfile=$work/$index-l2.txt:x=64:y=172:fontsize=16:fontcolor=0x202a26:enable='$enable'"
  filters+=",drawtext=fontfile=$mono:textfile=$work/$index-l3.txt:x=64:y=212:fontsize=16:fontcolor=0x202a26:enable='$enable'"
  index=$((index + 1))
done

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=0xeef1ee:size=640x360:rate=12,$filters" \
  -f lavfi -i "anullsrc=channel_layout=mono:sample_rate=16000" \
  -i "$vtt" \
  -t 152 -map 0:v -map 1:a -map 2:s \
  -c:v libx264 -preset veryslow -tune stillimage -crf 30 -pix_fmt yuv420p \
  -c:a aac -b:a 16k -c:s mov_text -metadata:s:s:0 language=eng \
  -movflags +faststart "$output"

printf 'PASS demo-course %s\n' "$output"
