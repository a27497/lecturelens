"""Pre-registered L4 metrics, bootstrap intervals and paired comparisons (PLAN.json "metrics"/"statistics", v4).

A row is one (path, repetition, item) outcome after the judge reveal:
  path, rep, item_id, lecture_id, answerable, status ("ok" | "failed"), abstained,
  verdict ("CORRECT" | "INCORRECT" | "UNDETERMINED" | None), vital_lenient, material_error,
  claims_supported, claims_total, citation_pairs_precise, citation_pairs_total, citations_relevant,
  citations_distinct, gold_evidence_hit (bool | None), cost_nano, latency_ms.
Failures and abstentions stay in every denominator they belong to; nothing is dropped.
"""

import math
from collections import defaultdict
from itertools import combinations

import numpy as np

SEED = 20261118
DRAWS = 10_000


def nearest_rank(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p * len(ordered))) - 1]


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return None
    phat = k / n
    centre = (phat + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def cohen_kappa(a, b):
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two equal, non-empty label lists")
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    expected = sum((a.count(label) / n) * (b.count(label) / n) for label in labels)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def mmss_ms(label):
    minutes, seconds = label.split(":")
    return (int(minutes) * 60 + int(seconds)) * 1000


def gold_evidence_hit(item, cited, evidence):
    """True if any cited Evidence overlaps the time range of a vital nugget cue (secondary metric).

    cited: Evidence ids the response cites; evidence: {id: {"startMs", "endMs"}} for the item's lecture.
    """
    ranges = [
        (mmss_ms(cue["start"]), mmss_ms(cue["end"]))
        for nugget in item["nuggets"]
        if nugget["importance"] == "vital"
        for cue in nugget["cues"]
    ]
    spans = [(evidence[e]["startMs"], evidence[e]["endMs"]) for e in cited if e in evidence]
    return any(s < end and e > start for s, e in spans for start, end in ranges)


# Each metric maps a row to (numerator, denominator) contributions.
def _answered(row):
    return row["status"] == "ok" and not row["abstained"]


def _correct(row):
    if not row["answerable"]:
        return 0, 0
    return int(_answered(row) and row["verdict"] == "CORRECT"), 1


def _vital_lenient(row):
    if not row["answerable"]:
        return 0, 0
    return (row["vital_lenient"] if _answered(row) else 0.0), 1


def _material_error(row):
    if not row["answerable"] or not _answered(row):
        return 0, 0
    return int(bool(row["material_error"])), 1


def _ratio_of(num_field, den_field):
    def metric(row):
        if not _answered(row) or not row[den_field]:
            return 0, 0
        return row[num_field], row[den_field]

    return metric


def _gold_hit(row):
    if not row["answerable"] or not _answered(row) or row["gold_evidence_hit"] is None:
        return 0, 0
    return int(row["gold_evidence_hit"]), 1


def _abstain_recall(row):
    if row["answerable"]:
        return 0, 0
    return int(row["status"] == "ok" and row["abstained"]), 1


def _false_refusal(row):
    if not row["answerable"]:
        return 0, 0
    return int(row["status"] == "ok" and row["abstained"]), 1


def _abstain_accuracy(row):
    right = row["status"] == "ok" and (row["abstained"] != row["answerable"])
    return int(right), 1


def _failure(row):
    return int(row["status"] != "ok"), 1


METRICS = {
    "strict_correct": _correct,
    "vital_lenient": _vital_lenient,
    "material_error": _material_error,
    "citation_recall": _ratio_of("claims_supported", "claims_total"),
    "citation_precision": _ratio_of("citation_pairs_precise", "citation_pairs_total"),
    "citation_precision_distinct": _ratio_of("citations_relevant", "citations_distinct"),
    "gold_evidence_hit": _gold_hit,
    "abstain_recall": _abstain_recall,
    "false_refusal": _false_refusal,
    "abstain_accuracy": _abstain_accuracy,
    "failure_rate": _failure,
}


def item_table(rows, metric):
    """{path: {item_id: (numerator, denominator)}} summed over repetitions."""
    table = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for row in rows:
        num, den = METRICS[metric](row)
        cell = table[row["path"]][row["item_id"]]
        cell[0] += num
        cell[1] += den
    return table


def _weights(items_by_lecture, item_index, draws, seed):
    """Stratified bootstrap counts: shape (draws, n_items)."""
    rng = np.random.default_rng(seed)
    weights = np.zeros((draws, len(item_index)))
    for lecture in sorted(items_by_lecture):
        members = np.array([item_index[i] for i in sorted(items_by_lecture[lecture])])
        picks = rng.integers(0, len(members), size=(draws, len(members)))
        for column in range(len(members)):
            np.add.at(weights, (np.arange(draws), members[picks[:, column]]), 1)
    return weights


def _ratio(weights, num, den):
    totals = weights @ den
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(totals > 0, (weights @ num) / totals, np.nan)


def bootstrap_weights(rows, *, draws=DRAWS, seed=SEED):
    """Items sorted by id and their stratified (by lecture) bootstrap counts, shape (draws, items)."""
    lectures = {row["item_id"]: row["lecture_id"] for row in rows}
    items = sorted(lectures)
    item_index = {item: i for i, item in enumerate(items)}
    by_lecture = defaultdict(set)
    for item, lecture in lectures.items():
        by_lecture[lecture].add(item)
    return items, _weights(by_lecture, item_index, draws, seed)


def summarize(rows, *, draws=DRAWS, seed=SEED, pairs_alpha=0.05):
    """Point estimates, 95% stratified-bootstrap CIs and Bonferroni-adjusted paired differences."""
    items, weights = bootstrap_weights(rows, draws=draws, seed=seed)
    by_lecture = {row["lecture_id"] for row in rows}
    paths = sorted({row["path"] for row in rows})
    pairs = list(combinations(paths, 2))
    adjusted = pairs_alpha / max(1, len(pairs))
    report = {"draws": draws, "seed": seed, "items": len(items), "lectures": len(by_lecture), "metrics": {}}
    for metric in METRICS:
        table = item_table(rows, metric)
        vectors, samples, entry = {}, {}, {}
        for path in paths:
            num = np.array([table[path][item][0] if item in table[path] else 0.0 for item in items])
            den = np.array([table[path][item][1] if item in table[path] else 0.0 for item in items])
            vectors[path] = (num, den)
            samples[path] = _ratio(weights, num, den)
            point = float(num.sum() / den.sum()) if den.sum() else None
            low, high = np.nanpercentile(samples[path], [2.5, 97.5]) if den.sum() else (None, None)
            entry[path] = {
                "estimate": point,
                "numerator": float(num.sum()),
                "denominator": float(den.sum()),
                "ci95": None if point is None else [float(low), float(high)],
            }
        differences = {}
        for a, b in pairs:
            if entry[a]["estimate"] is None or entry[b]["estimate"] is None:
                continue
            delta = samples[a] - samples[b]
            low, high = np.nanpercentile(delta, [100 * adjusted / 2, 100 * (1 - adjusted / 2)])
            differences[f"{a}-{b}"] = {
                "estimate": entry[a]["estimate"] - entry[b]["estimate"],
                "ci_bonferroni": [float(low), float(high)],
                "level": 1 - adjusted,
            }
        report["metrics"][metric] = {"paths": entry, "differences": differences}
    return report


def repetition_range(rows, metric):
    """Min-max of the metric over repetitions, per path."""
    out = {}
    for path in sorted({r["path"] for r in rows}):
        values = []
        for rep in sorted({r["rep"] for r in rows if r["path"] == path}):
            num = den = 0.0
            for row in rows:
                if row["path"] == path and row["rep"] == rep:
                    n, d = METRICS[metric](row)
                    num, den = num + n, den + d
            if den:
                values.append(num / den)
        out[path] = [min(values), max(values)] if values else None
    return out


def mcnemar_pairs(rows, rep=1, metric="strict_correct"):
    by = defaultdict(dict)
    for row in rows:
        if row["rep"] == rep:
            num, den = METRICS[metric](row)
            if den:
                by[row["path"]][row["item_id"]] = bool(num)
    result = {}
    for a, b in combinations(sorted(by), 2):
        shared = sorted(set(by[a]) & set(by[b]))
        only_a = sum(by[a][i] and not by[b][i] for i in shared)
        only_b = sum(by[b][i] and not by[a][i] for i in shared)
        result[f"{a}-{b}"] = {
            "n": len(shared),
            "only_first": only_a,
            "only_second": only_b,
            "p_exact": mcnemar_exact(only_a, only_b),
        }
    return result


def latency_cost(rows, *, draws=DRAWS, seed=SEED):
    """P50/P95 latency (nearest rank over every attempt) and mean cost per attempt.

    Intervals reuse the item-level stratified bootstrap weights of summarize(): a resampled item
    contributes all of its attempts as many times as it was drawn.
    """
    items, weights = bootstrap_weights(rows, draws=draws, seed=seed)
    index = {item: i for i, item in enumerate(items)}
    out = {}
    for path in sorted({r["path"] for r in rows}):
        mine = [r for r in rows if r["path"] == path]
        entry = {"attempts": len(mine)}
        for field in ("latency_ms", "cost_nano"):
            per_item = defaultdict(list)
            for row in mine:
                if row[field] is not None:
                    per_item[index[row["item_id"]]].append(row[field])
            values = [v for vs in per_item.values() for v in vs]
            entry[field + "_samples"] = len(values)
            if not values:
                continue
            columns = sorted(per_item)
            stats = {"p50": [], "p95": [], "mean": []}
            for draw in weights:
                expanded = [v for c in columns for v in per_item[c] * int(draw[c])]
                if not expanded:
                    continue
                if field == "latency_ms":
                    stats["p50"].append(nearest_rank(expanded, 0.5))
                    stats["p95"].append(nearest_rank(expanded, 0.95))
                else:
                    stats["mean"].append(sum(expanded) / len(expanded))
            if field == "latency_ms":
                for name, p in (("p50", 0.5), ("p95", 0.95)):
                    entry[name + "_ms"] = nearest_rank(values, p)
                    entry[name + "_ms_ci95"] = [
                        float(np.percentile(stats[name], 2.5)),
                        float(np.percentile(stats[name], 97.5)),
                    ]
            else:
                entry["mean_cost_usd"] = sum(values) / len(values) / 1e9
                entry["mean_cost_usd_ci95"] = [
                    float(np.percentile(stats["mean"], 2.5) / 1e9),
                    float(np.percentile(stats["mean"], 97.5) / 1e9),
                ]
                entry["total_cost_usd"] = sum(values) / 1e9
        out[path] = entry
    return out
