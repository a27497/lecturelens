"""Frozen-qrel metrics and paired family/course uncertainty, not quality certification."""

import hashlib
import math
import random
from collections import Counter, defaultdict
from itertools import product

import numpy as np

from ..benchmark.core import STRATEGIES, percentile, retrieval_metrics, validate_dataset


def validate_v2(corpus, dataset, plan):
    validate_dataset(corpus, dataset)
    courses = set(corpus["courses"])
    development, holdout = set(plan["development_courses"]), set(plan["holdout_courses"])
    if development & holdout or development | holdout != courses:
        raise ValueError("Course split overlaps or omits courses")
    lookup = {e["evidence_id"]: e for c in corpus["courses"].values() for e in c["evidence"]}
    if len(lookup) != sum(len(c["evidence"]) for c in corpus["courses"].values()):
        raise ValueError("Evidence IDs must be globally unique")
    queries = set()
    for case in dataset["cases"]:
        if case["query"] in queries:
            raise ValueError("Duplicate query")
        queries.add(case["query"])
        expected = "development" if case["course"] in development else "holdout"
        if case["split"] != expected or not case.get("family") or case["language"] not in {"en", "zh"}:
            raise ValueError("Invalid split/family/language")
        if case.get("cross_lecture"):
            lectures = [
                {lookup[e]["lecture_id"] for e in aspect["evidence_ids"]} for aspect in case["aspects"]
            ]
            if len(lectures) < 2 or any(len(s) != 1 for s in lectures) or len(set.union(*lectures)) < 2:
                raise ValueError("Cross-lecture gold must span distinct lectures")
        for aspect in case["aspects"]:
            if not aspect.get("required_fact") or not aspect.get("source_locator"):
                raise ValueError("Missing source-supported annotation")
    for name in courses:
        selected = [c for c in dataset["cases"] if c["course"] == name]
        if len(selected) != plan["questions_per_course"]:
            raise ValueError("Question plan count differs")
        if sum(c["answerable"] for c in selected) != plan["answerable_per_course"]:
            raise ValueError("Answerability plan differs")
        if sum(c.get("cross_lecture", False) for c in selected) != plan["cross_lecture_per_course"]:
            raise ValueError("Cross-lecture plan differs")
        if sum(c["language"] == "zh" for c in selected) != plan["chinese_per_course"]:
            raise ValueError("Language plan differs")


def bootstrap_weights(cases, draws, seed, *, courses=False):
    """Paired cluster draws shared across methods; duplicate families stay together.

    Within a course sample question families with replacement, retaining all
    members of each selected family. Optionally resample courses first. This does
    not pretend correlated questions or bilingual variants are independent.
    """
    groups = defaultdict(lambda: defaultdict(list))
    for index, case in enumerate(cases):
        groups[case["course"]][case["family"]].append(index)
    names = sorted(groups)
    if not names or draws < 1:
        raise ValueError("Empty bootstrap population")
    rng = random.Random(seed)
    weights = np.zeros((draws, len(cases)), dtype=np.int32)
    for row in weights:
        selected = rng.choices(names, k=len(names)) if courses else names
        for course in selected:
            families = sorted(groups[course])
            for family in rng.choices(families, k=len(families)):
                row[groups[course][family]] += 1
    return weights


def interval(values, alpha=0.05):
    return [float(np.quantile(values, alpha / 2)), float(np.quantile(values, 1 - alpha / 2))]


def mean_interval(values, weights, alpha=0.05):
    values = np.asarray(values, dtype=float)
    distribution = weights @ values / weights.sum(axis=1)
    return {"estimate": float(np.mean(values)), "ci": interval(distribution, alpha), "n": len(values)}


def latency_interval(values, weights, p):
    # Repeats are not independent observations: each query has one timed retrieval.
    values = np.asarray(values)
    draws = [percentile(np.repeat(values, row).tolist(), p) for row in weights]
    return {"estimate_ms": percentile(values.tolist(), p), "ci95_ms": interval(draws), "n": len(values)}


def wilson(positives, n):
    if not n:
        return None
    z = 1.959963984540054
    rate = positives / n
    center = (rate + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0, center - half), min(1, center + half)]


def course_sign_flip(values, cases):
    groups = defaultdict(list)
    for value, case in zip(values, cases, strict=True):
        groups[case["course"]].append(value)
    effects = [float(np.mean(group)) for _, group in sorted(groups.items())]
    observed = abs(float(np.mean(effects)))
    null = [
        abs(float(np.mean(np.asarray(effects) * signs))) for signs in product((-1, 1), repeat=len(effects))
    ]
    return sum(value >= observed - 1e-12 for value in null) / len(null)


def failure_buckets(row, case, lookup, k=3):
    ids = [h["evidence_id"] for h in row["hits"]]
    if row.get("error_type"):
        return ["retrieval_error"]
    if not case["answerable"]:
        return ["no_answer_candidate_returned"] if ids else []
    missing = [a for a in case["aspects"] if not set(a["evidence_ids"]) & set(ids[:k])]
    negative = bool(set(case["hard_negative_ids"]) & set(ids[:k]))
    buckets = []
    if missing:
        if any(not set(a["evidence_ids"]) & set(ids) for a in missing):
            buckets.append("not_recalled_in_candidates")
        else:
            buckets.append("ranked_below_context")
        groups = [lookup[e]["equivalence_group"] for e in ids[:k]]
        if len(set(groups)) < len(groups):
            buckets.append("original_translation_duplicate")
    if negative:
        buckets.append("hard_negative_in_context")
    return buckets


def summarize_scope(rows, cases, config, lookup, name):
    mapping = {(r["case_id"], r["strategy"]): r for r in rows}
    answerable = [c for c in cases if c["answerable"]]
    no_answer = [c for c in cases if not c["answerable"]]
    seed = config["bootstrap_seed"] + int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    draws = config["bootstrap_draws"]
    fixed = bootstrap_weights(answerable, draws, seed)
    hierarchical = bootstrap_weights(answerable, draws, seed, courses=True)
    latency_weights = bootstrap_weights(cases, draws, seed)
    results, paired_values, bad_cases = {}, {}, []
    for method in STRATEGIES:
        selected = [mapping[c["id"], method] for c in cases]
        quality = {}
        for k in config["metric_ks"]:
            quality[str(k)] = {}
            values = [
                retrieval_metrics([h["evidence_id"] for h in mapping[c["id"], method]["hits"]], c, k)
                for c in answerable
            ]
            for metric in ("recall", "mrr", "ndcg", "evidence_coverage"):
                vector = [v[metric] for v in values]
                quality[str(k)][metric] = {
                    **mean_interval(vector, fixed),
                    "ci95_course_family": mean_interval(vector, hierarchical)["ci"],
                }
                if k == config["context_k"] and metric == "evidence_coverage":
                    paired_values[method] = np.asarray(vector)
        latency = [r["latency_ms"] for r in selected]
        flags = [bool(mapping[c["id"], method]["hits"]) for c in no_answer]
        failures = []
        for case in cases:
            row = mapping[case["id"], method]
            buckets = failure_buckets(row, case, lookup, config["context_k"])
            if buckets:
                # Primary buckets are exclusive; additional tags are diagnostic,
                # not counterfactual proof that a particular ranking cause failed.
                priority = (
                    "retrieval_error",
                    "no_answer_candidate_returned",
                    "not_recalled_in_candidates",
                    "hard_negative_in_context",
                    "original_translation_duplicate",
                    "ranked_below_context",
                )
                primary = next(b for b in priority if b in buckets)
                failures.append((primary, buckets))
                bad_cases.append(
                    {
                        "case_id": case["id"],
                        "strategy": method,
                        "split": case["split"],
                        "query": case["query"],
                        "primary_bucket": primary,
                        "tags": buckets,
                        "hits": row["hits"],
                        "gold_aspects": case["aspects"],
                        "error_type": row.get("error_type"),
                    }
                )
        primary_counts = Counter(p for p, _ in failures)
        tag_counts = Counter(t for _, tags in failures for t in tags)
        results[method] = {
            "queries": len(cases),
            "answerable_queries": len(answerable),
            "no_answer_queries": len(no_answer),
            "metrics": quality,
            "latency": {
                "p50": latency_interval(latency, latency_weights, 0.5),
                "p95": latency_interval(latency, latency_weights, 0.95),
            },
            "no_answer_candidate_returned": {
                "count": sum(flags),
                "n": len(flags),
                "rate": sum(flags) / len(flags) if flags else None,
                "wilson_ci95": wilson(sum(flags), len(flags)),
            },
            "retrieval_errors": sum(bool(r.get("error_type")) for r in selected),
            "failures": {
                "n": len(failures),
                "population": len(cases),
                "primary_counts": dict(primary_counts),
                "primary_share_of_failures": {k: v / len(failures) for k, v in primary_counts.items()},
                "tag_counts": dict(tag_counts),
                "tag_share_of_failures": {k: v / len(failures) for k, v in tag_counts.items()},
            },
        }
    paired = {}
    for method in STRATEGIES[1:]:
        diff = paired_values[method] - paired_values["dense"]
        paired[method + "_minus_dense"] = {
            **mean_interval(diff, fixed, alpha=0.05 / 3),
            "ci_course_family_bonferroni": mean_interval(diff, hierarchical, alpha=0.05 / 3)["ci"],
            "metric": "Evidence Coverage@3",
            "simultaneous_family": "three prespecified comparisons to Dense",
            "course_sign_flip_p_two_sided": course_sign_flip(diff, answerable),
            "course_sign_flip_p_bonferroni": min(1, 3 * course_sign_flip(diff, answerable)),
        }
    return {
        "scope": name,
        "courses": sorted({c["course"] for c in cases}),
        "methods": results,
        "paired_primary_comparisons": paired,
    }, bad_cases


def report(rows, dataset, corpus, config):
    cases = dataset["cases"]
    expected = {(c["id"], s) for c in cases for s in STRATEGIES}
    observed = [(r["case_id"], r["strategy"]) for r in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("Missing, duplicate or foreign query/method observation")
    lookup = {e["evidence_id"]: e for c in corpus["courses"].values() for e in c["evidence"]}
    by_id = {c["id"]: c for c in cases}
    for row in rows:
        if row["split"] != by_id[row["case_id"]]["split"]:
            raise ValueError("Observation split differs from frozen case")
        valid = {e["evidence_id"] for e in corpus["courses"][by_id[row["case_id"]]["course"]]["evidence"]}
        ids = [h["evidence_id"] for h in row["hits"]]
        if (
            len(ids) != len(set(ids))
            or not set(ids) <= valid
            or not math.isfinite(row["latency_ms"])
            or row["latency_ms"] < 0
        ):
            raise ValueError("Invalid rank/latency/scope observation")
    summaries, bad = {}, []
    for scope in ("development", "holdout", "all", "zh", "en", "cross-lecture"):
        chosen = [
            c
            for c in cases
            if scope == "all"
            or c["split"] == scope
            or c["language"] == scope
            or scope == "cross-lecture"
            and c.get("cross_lecture")
        ]
        result, failures = summarize_scope(rows, chosen, config, lookup, scope)
        summaries[scope] = result
        if scope == "all":
            bad = failures
    return summaries, bad
