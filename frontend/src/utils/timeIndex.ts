/** Half-open intervals; overlaps prefer the latest start, then original input order. */
export function createTimeIndex<T>(items: readonly T[], start: (item: T) => number, end: (item: T) => number) {
  const ranges = items.map((item, order) => ({ item, order, start: start(item), end: end(item) }))
    .filter(r => Number.isFinite(r.start) && Number.isFinite(r.end) && r.start >= 0 && r.end > r.start)
    .sort((a, b) => a.start - b.start || b.order - a.order);
  const times = [...new Set(ranges.flatMap(r => [r.start, r.end]))].sort((a, b) => a - b);
  const heap: number[] = [];
  const spans: { at: number; item: T | null }[] = [];
  let next = 0;
  function push(rank: number) {
    heap.push(rank);
    let i = heap.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (heap[p]! >= heap[i]!) break;
      [heap[p], heap[i]] = [heap[i]!, heap[p]!]; i = p;
    }
  }
  function pop() {
    const last = heap.pop()!;
    if (!heap.length) return;
    heap[0] = last;
    let i = 0;
    while (i * 2 + 1 < heap.length) {
      let child = i * 2 + 1;
      if (child + 1 < heap.length && heap[child + 1]! > heap[child]!) child++;
      if (heap[i]! >= heap[child]!) break;
      [heap[i], heap[child]] = [heap[child]!, heap[i]!]; i = child;
    }
  }
  for (const at of times) {
    while (next < ranges.length && ranges[next]!.start <= at) push(next++);
    while (heap.length && ranges[heap[0]!]!.end <= at) pop();
    const item = heap.length ? ranges[heap[0]!]!.item : null;
    if (!spans.length || spans[spans.length - 1]!.item !== item) spans.push({ at, item });
  }
  return (at: number): T | null => {
    if (!Number.isFinite(at) || at < 0) return null;
    let lo = 0, hi = spans.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (spans[mid]!.at <= at) lo = mid + 1; else hi = mid;
    }
    return lo ? spans[lo - 1]!.item : null;
  };
}
