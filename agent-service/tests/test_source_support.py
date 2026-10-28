import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "eval/source-support"
spec = importlib.util.spec_from_file_location("source_support", ROOT / "measure.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs():
    return (
        json.loads((ROOT / "example-candidate.json").read_text()),
        json.loads((ROOT / "example-ratings.json").read_text()),
    )


def test_resolvable_citations_do_not_imply_semantic_support():
    result = module.measure(*inputs())
    assert result["citation_resolution_rate"] == 1 and result["source_support_rate"] == 0.5
    assert result["unsupported"] == 1 and result["quality_status"] == "MOCK_NOT_QUALITY"


@pytest.mark.parametrize("defect", ["identity", "missing", "quote", "revision", "duplicate"])
def test_invalid_judgment_bindings_fail_closed(defect):
    candidate, ratings = inputs()
    if defect == "identity":
        candidate["items"][0]["claim"] = "Changed after evaluation"
    elif defect == "missing":
        ratings["judgments"].pop()
    elif defect == "duplicate":
        ratings["judgments"].append(ratings["judgments"][0])
    elif defect == "quote":
        ratings["judgments"][0]["quotes"][0]["text"] = "Not in the cited text"
    elif defect == "revision":
        candidate["revision"] = 2
        ratings["candidate_sha256"] = module.digest(candidate)
    with pytest.raises(ValueError):
        module.measure(candidate, ratings)
