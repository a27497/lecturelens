"""Bounded mathematical scales, never benchmark timings or algorithm proofs."""


def compare_scales(input_sizes):
    if type(input_sizes) is not list or not 1 <= len(input_sizes) <= 4:
        return {"status": "unsupported", "reason": "Choose one through four bounded hypothetical sizes."}
    rows = []
    for size in input_sizes:
        if type(size) is not int or not 1 <= size <= 2**20 or size & (size - 1):
            return {
                "status": "unsupported",
                "reason": "Use powers of two from 1 through 2^20 for exact halving levels.",
            }
        sequence = [size]
        while sequence[-1] > 1:
            sequence.append(sequence[-1] // 2)
        rows.append(
            {
                "input_size": size,
                "linear_scale": size,
                "log2_scale": len(sequence) - 1,
                "halving_sizes": sequence,
            }
        )
    if len(set(input_sizes)) != len(input_sizes):
        return {"status": "unsupported", "reason": "Choose distinct sizes."}
    return {
        "status": "computed",
        "semantics": "growth_scales_v1",
        "rows": rows,
        "class_substitution": {
            "input_relation": "n=2^k",
            "linear_class": "Theta(2^k)",
            "logarithmic_class": "Theta(k)",
        },
        "interpretation": "For each hypothetical input n, k=log2(n) halving levels and n=2^k. Linear scale n versus logarithmic scale k. These are mathematical scales, not exact comparisons, elapsed times, or a new algorithm. A Θ bound is not a numeric function value: label n and k as representative growth scales, never Θ(n)=n or Θ(log n)=k exact values. Course support and the learner goal still require independent review.",
    }
