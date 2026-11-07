"""Two retained delivery failures and explicit v18 capacity measurements, offline only."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    spec = importlib.util.spec_from_file_location(
        "retained_v14", ROOT / "scripts/dev/v14_delivery_diagnosis.py"
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    frames = {row["sequence"]: row for row in old.retained_frames()}
    rows = []
    for sequence in [24, 25, 31, 32]:
        frame = frames[sequence]
        text = frame["proposals"][0]["arguments"]["text"]
        rows.append(
            {
                "sequence": sequence,
                "turn_key": frame["turn_key"],
                "source": str(old.RUN / "turns.jsonl"),
                "proposal_sha256": hashlib.sha256(
                    json.dumps(frame["proposals"][0], sort_keys=True).encode()
                ).hexdigest(),
                "counts": old.citation_cost(text),
                "fits_old_1600": len(text) <= 1600,
                "fits_new_4096_size_only": len(text) <= 4096,
                "historical_verdict": "FAIL_UNCHANGED",
                "new_generation": "NOT_RUN",
                "replay": "RECONSTRUCTED_FROM_PARSED_PROPOSAL_NOT_ORIGINAL_RESPONSE_BYTES",
            }
        )
    from lecturelens_real_eval.tutor.usable_runtime import render

    answer = [
        {"kind": "explanation", "text": "中" * 900, "evidence_id": str(i) * 64}
        for i in range(4)
    ]
    feedback = [{"text": "中" * 384, "evidence_id": str(i) * 64} for i in range(2)]
    result = {
        "scope": "BOUNDED_LENGTH_CHECK_NOT_FULL_AUDIT_OR_NEW_GENERATION",
        "historical": rows,
        "max_rendered_answer": len(render(answer)),
        "max_rendered_feedback": len(render(feedback, feedback=True)),
        "character_unit": "Python len / Unicode code points; labels, whitespace and full canonical IDs included",
        "maximum_wire_liability_nano_usd": 12 * (65536 * 300 + 4096 * 1200),
        "reserved_plus_settled_cap_nano_usd": 300000000,
        "cost_usd": "0",
        "real_model_calls": 0,
        "embedding_calls": 0,
        "reviewer_calls": 0,
    }
    path = ROOT / ".data/tutor-usability-v18/length-measurement.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
