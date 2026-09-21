"""Bounded asymptotic comparisons; no fabricated constants or numeric break-even."""


def cost_application(scenario, language, evidence_ids):
    if scenario not in {"single_lookup", "repeated_lookups"} or language not in {"en", "zh"}:
        raise ValueError("Unsupported cost scenario or language")
    if language == "zh":
        question = (
            "图书馆只需查询一次未排序的访客名单。管理员计划先排序再二分查找，并声称总成本只取决于最后的二分查询。指出遗漏的阶段，并与直接逐项扫描比较总成本。"
            if scenario == "single_lookup"
            else "系统对内容不变的名单执行反复查询，却在每次查询前重新排序。如何修改这一计划？区分一次性准备成本和每次查询成本，并与逐次扫描比较。"
        )
        points = [
            "直接逐项扫描无需排序准备，每次查询为 O(n)。",
            "排序准备为 O(n log n)，之后每次二分查询为 O(log n)。"
            + (
                "仅查询一次时总成本由排序主导，为 O(n log n)，逐项扫描避免该准备开销。"
                if scenario == "single_lookup"
                else "需要权衡一次准备开销与后续每次查询节省的成本，多次查询可分摊准备成本。"
            ),
        ]
    else:
        question = (
            "A librarian will query an unsorted visitor roster once. They plan to sort then binary search, but count only the final binary search as the total cost. Identify the omitted stage and compare the total cost with a direct linear scan."
            if scenario == "single_lookup"
            else "A system repeatedly queries an unchanging roster but sorts it again before every query. Revise this plan, distinguishing one-time preparation from per-query cost, and compare it with repeated linear scans."
        )
        points = [
            "Linear scanning requires no sorting preparation and costs O(n) per query.",
            "Sorting costs O(n log n) once; each subsequent binary search costs O(log n). "
            + (
                "For one query the total is O(n log n), dominated by sorting; a linear scan avoids this preparation."
                if scenario == "single_lookup"
                else "Weigh the upfront preparation against savings on subsequent queries; repeated queries can spread that preparation cost."
            ),
        ]
    return {"question": question, "answer_points": points, "evidence_ids": list(evidence_ids)}
