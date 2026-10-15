"""Build fixed questions and explicit Chinese factual adaptations before scoring.

Native Evidence is a normalized PDF extraction; see corpus/source-downloads.
Annotations are Codex source-based model assistance, not independent human gold.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRANSLATIONS = {
    "algorithms": [
        "BFS 按层从起点 s 探索。第 0 层只有 s；第 i 层是用 i 条边能到达且不能用更少边到达的顶点。",
        "DFS 像探索迷宫：沿路径前进，受阻后回溯，再递归访问未见过的邻居；父指针用于避免重复访问顶点。",
        "Dijkstra 假设所有边权非负。从未确定的顶点中反复选择暂定距离最小者，加入已确定集合并松弛其出边。",
    ],
    "linear": [
        "将 b 投影到 a 张成的直线，最近点的几何特征是误差 b-p 与 a 垂直。",
        "当 Ax=b 没有精确解时，用最小二乘使误差向量 Ax-b 的各分量平方和最小。",
        "标准正交基的不同向量两两垂直，每个向量都是单位长度。列向量内积给出对角为一、其余为零的矩阵。",
    ],
    "calculus": [
        "两个向量的点积等于两者长度乘积再乘夹角的余弦；这同时描述长度与角度。",
        "平面行列式是有向面积。方向不同，行列式可以为正或负，因此普通面积要取绝对值。",
        "A 叉乘 B 与 B 叉乘 A 的方向不同。交换参数改变右手规则确定的方向，不能把叉乘看成普通的可交换乘法。",
    ],
    "probability": [
        "样本空间是可能结果的集合。列出的结果必须互斥且穷尽，建模时还要选择恰当的描述粒度。",
        "给定 B 时，B 是新的范围。条件概率 P(A|B)=P(A∩B)/P(B)，仅在 P(B) 非零时定义；零概率条件在此定义中无意义。",
        "A 与 B 独立表示 A 的发生不提供关于 B 的信息；交集概率等于边缘概率的乘积。给定额外事件可能改变独立性。",
    ],
    "economics": [
        "消费者行为的基本构件是效用最大化：根据偏好，在可用资源所形成的预算约束下选择消费组合。",
        "两种商品的预算线表示收入可负担的组合。全部收入买某一种商品时，数量截距是收入除以该商品价格。",
        "正常品的收入弹性为正，收入增加会购买更多；劣等品的收入弹性为负，收入增加会购买更少。",
    ],
    "quantum": [
        "量子力学不对所有实验给出确定的单次结果，而预测各结果的概率；这与经典确定性观点不同。",
        "干涉仪的两分量复数向量表示上、下两条路径的概率幅，各分量模平方给出对应路径的概率。",
        "固定频率增加光强，会使更多光子到达而增加光电流，但不会改变单个光子及射出光电子的能量。",
    ],
}
# IDs of the specific original facts translated above, not guessed from rankings.
TRANSLATED_INDICES = {
    "algorithms": [0, 4, 8],
    "linear": [0, 4, 8],
    "calculus": [0, 4, 8],
    "probability": [0, 4, 8],
    "economics": [0, 4, 8],
    "quantum": [0, 4, 8],
}
HARD_NEGATIVE = {
    "algorithms": ["l2-p02-e00", "l3-p01-e00", "l1-p06-e00"],
    "linear": ["l3-p01-e01", "l1-p06-e01", "l1-p07-e01"],
    "calculus": ["l2-p12-e00", "l1-p06-e01", "l3-p01-e03"],
    "probability": ["l3-p01-e01", "l1-p03-e00", "l2-p02-e00"],
    "economics": ["l1-p02-e04", "l1-p10-e00", "l2-p08-e00"],
    "quantum": ["l2-p07-e01", "l1-p09-e02", "l2-p01-e01"],
}


def main():
    corpus = json.loads((ROOT / "corpus.json").read_text())
    seeds = json.loads((ROOT / "annotation-seeds.json").read_text())
    plan = json.loads((ROOT / "split-plan.json").read_text())
    assert not (ROOT / "freeze.json").exists(), "Never modify an already frozen dataset"
    cases = []
    for course, single in seeds["single"].items():
        evidence = corpus["courses"][course]["evidence"]
        originals = {e["evidence_id"]: e for e in evidence if e["language"] == "en"}
        assert len(evidence) == len(originals), (
            "Run on the native corpus, not a previously adapted corpus"
        )
        alternatives = {}
        for ordinal, index in enumerate(TRANSLATED_INDICES[course]):
            eid = "v2-" + course + "-" + single[index][2]
            original = originals[eid]
            text = TRANSLATIONS[course][ordinal]
            translated = {
                **original,
                "evidence_id": eid + "-zh",
                "language": "zh",
                "text": text,
                "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                "adaptation": "Codex partial factual Chinese translation; not a verbatim full-paragraph translation",
                "derived_from": eid,
            }
            evidence.append(translated)
            alternatives[eid] = [eid, eid + "-zh"]

        def aspect(
            index,
            single=single,
            course=course,
            originals=originals,
            alternatives=alternatives,
        ):
            _en, _zh, loc, fact = single[index]
            eid = "v2-" + course + "-" + loc
            assert eid in originals, eid
            return {
                "required_fact": fact,
                "evidence_ids": alternatives.get(eid, [eid]),
                "source_locator": {
                    k: originals[eid][k]
                    for k in [
                        "lecture_id",
                        "page",
                        "normalized_character_range",
                        "source_url",
                        "source_sha256",
                    ]
                },
            }

        split = "development" if course in plan["development_courses"] else "holdout"
        categories = [
            "lexical",
            "semantic",
            "multi-condition",
            "confusing-evidence-hard-negative",
        ]
        for index, (en, zh, loc, fact) in enumerate(single):
            language = "en" if index % 2 == 0 else "zh"
            negative = []
            if index % 4 == 3:
                negative = ["v2-" + course + "-" + HARD_NEGATIVE[course][index // 4]]
            cases.append(
                {
                    "id": f"{course}-q{index + 1:02d}",
                    "course": course,
                    "split": split,
                    "family": course + "-" + loc.split("-p")[0],
                    "language": language,
                    "query": en if language == "en" else zh,
                    "category": categories[index % 4],
                    "answerable": True,
                    "aspects": [aspect(index)],
                    "hard_negative_ids": negative,
                    "hard_negative_rationale": "Related but insufficient for the specific question, or an explicitly corrected false teaching premise."
                    if negative
                    else None,
                    "no_answer_reason": None,
                }
            )
        for offset, (en, zh, indices) in enumerate(seeds["cross"][course]):
            language = "en" if offset % 2 == 0 else "zh"
            aspects = [aspect(i) for i in indices]
            assert len({a["source_locator"]["lecture_id"] for a in aspects}) == 2
            cases.append(
                {
                    "id": f"{course}-q{13 + offset:02d}",
                    "course": course,
                    "split": split,
                    "family": course + "-cross",
                    "language": language,
                    "query": en if language == "en" else zh,
                    "category": "cross-section",
                    "cross_lecture": True,
                    "answerable": True,
                    "aspects": aspects,
                    "hard_negative_ids": [],
                    "no_answer_reason": None,
                }
            )
        for offset, (en, zh, reason) in enumerate(seeds["no_answer"][course]):
            language = "en" if offset % 2 == 0 else "zh"
            cases.append(
                {
                    "id": f"{course}-q{17 + offset:02d}",
                    "course": course,
                    "split": split,
                    "family": course + "-no-answer",
                    "language": language,
                    "query": en if language == "en" else zh,
                    "category": "exception-no-answer",
                    "answerable": False,
                    "aspects": [],
                    "hard_negative_ids": [],
                    "no_answer_reason": reason,
                }
            )
    metadata = {
        "id": "retrieval-v2",
        "annotation": {
            "type": seeds["annotation_type"],
            "human_annotators": 0,
            "independent_review": False,
            "source_review": "Every positive locator was inspected before scoring. Sparse anchored qrels, not exhaustive human judgments. No-answer means unavailable in this frozen text-only snapshot, not the whole course.",
        },
        "cases": cases,
    }
    (ROOT / "cases.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    (ROOT / "corpus.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n"
    )
    print(len(cases), sum(len(c["evidence"]) for c in corpus["courses"].values()))


if __name__ == "__main__":
    main()
