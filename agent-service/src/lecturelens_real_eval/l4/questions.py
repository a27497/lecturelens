"""Question-set rules and the freeze record (PLAN.json "question_set").

FREEZE.json binds the PLAN, the asset lock, the gold-audit result and both question files by
sha256. Every runner verifies it before sending anything, so an edited item cannot be scored.
"""

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ORDER = [
    "definition_or_fact",
    "explanation_why",
    "procedure_or_worked_example",
    "comparison_within_lecture",
    "cross_segment_two_timestamps_5min_apart",
    "near_miss_topic_from_other_lecture_of_same_course",
    "detail_on_topic_not_stated_in_lecture",
    "out_of_domain",
]
ANSWERABLE = set(ORDER[:5])


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_set(data, rules):
    """Structural rules only; caption quotes are checked by the authoring validator."""
    errors = []
    by_lecture = {}
    for item in data["items"]:
        by_lecture.setdefault(item["lecture_id"], []).append(item)
        if item["answerable"] != (item["category"] in ANSWERABLE):
            errors.append(f"{item['item_id']}: answerable flag disagrees with category")
        if item["language"] != ("zh" if item["position"] % 2 else "en"):
            errors.append(f"{item['item_id']}: language rule")
        if item["answerable"] and not 1 <= len(item["key_points"]) <= 4:
            errors.append(f"{item['item_id']}: key point count")
    rule = rules["dev_lecture" if data["split"] == "dev" else "holdout_lecture"]
    expected = Counter({**rule["answerable"], **rule["should_abstain"]})
    for lecture, items in sorted(by_lecture.items()):
        if Counter(i["category"] for i in items) != expected:
            errors.append(f"{lecture}: category counts")
    ids = [i["item_id"] for i in data["items"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate item ids")
    return errors


def write_freeze(root, *, audit_path, note=""):
    root = Path(root)
    plan = json.loads((root / "PLAN.json").read_bytes())
    rules = plan["question_set"]["fixed_rules"]
    record = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "plan_sha256": file_sha(root / "PLAN.json"),
        "assets_lock_sha256": file_sha(root / "sources/assets.lock.json"),
        "gold_audit_sha256": file_sha(audit_path),
        "sets": {},
    }
    for split in ("dev", "holdout"):
        path = root / "questions" / f"questions.{split}.json"
        data = json.loads(path.read_text())
        errors = check_set(data, rules)
        if errors:
            raise ValueError(f"{split}: {errors[:5]}")
        record["sets"][split] = {
            "sha256": file_sha(path),
            "items": len(data["items"]),
            "answerable": sum(i["answerable"] for i in data["items"]),
            "ids": [i["item_id"] for i in data["items"]],
        }
    target = root / "FREEZE.json"
    with target.open("x") as out:
        json.dump(record, out, indent=2)
        out.write("\n")
    target.chmod(0o600)
    return file_sha(target)


def load_frozen(root, split):
    """Return the frozen items of a split, refusing any drift from FREEZE.json."""
    root = Path(root)
    freeze = json.loads((root / "FREEZE.json").read_text())
    if freeze["plan_sha256"] != file_sha(root / "PLAN.json"):
        raise ValueError("FREEZE_PLAN_CHANGED")
    path = root / "questions" / f"questions.{split}.json"
    if file_sha(path) != freeze["sets"][split]["sha256"]:
        raise ValueError("FREEZE_QUESTIONS_CHANGED")
    items = json.loads(path.read_text())["items"]
    if [i["item_id"] for i in items] != freeze["sets"][split]["ids"]:
        raise ValueError("FREEZE_IDS_CHANGED")
    return items
