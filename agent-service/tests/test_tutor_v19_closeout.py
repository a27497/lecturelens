"""Authored HTTP fixtures verify the frozen protocol, never real model quality."""

import copy
import json
import os
from pathlib import Path

import jsonschema
import pytest
import test_tutor_v19 as prior

from lecturelens_real_eval.tutor.selection_smoke import execute

offline = prior.offline


@pytest.mark.parametrize(
    "first,second",
    [(None, None), ("format", None), ("span", None), ("format", "span"), ("span", "format")],
)
def test_teaching_through_frozen_http_entry_and_one_shared_correction(first, second):
    output = Path(os.environ["TUTOR_SELECTION_OUTPUT"]) / f"teaching-http-{first}-{second}"
    observed = []

    def response(wire, index):
        body = json.loads(wire["messages"][-1]["content"])
        observed.append(copy.deepcopy(wire))
        assert "reference_points" not in wire["messages"][-1]["content"]
        assert "scoring" not in wire["messages"][-1]["content"]
        searches = sum(o["tool"] == "search_tutor_evidence" for o in body["observations"])
        # Two observations on the first turn exercise the third ordinary decision
        # followed by the one prepaid correction through the actual HTTP channel.
        if not searches or not body["history"] and searches == 1:
            name = "search_tutor_evidence"
            arguments = dict(query="loop length first index print odds")
        else:
            name = "finish_tutor_turn"
            schema = next(s["function"]["parameters"] for s in wire["tools"] if s["function"]["name"] == name)
            if body["socratic"]:
                arguments = dict(
                    outcome="socratic_prompt",
                    hint=dict(span=prior.span(body, "length = length + 1"), intent="locate_body"),
                )
            else:
                assert schema["$defs"]["Explanation"]["properties"]["text"]["maxLength"] == 900
                arguments = prior.complete(body)
                if body["evaluation_required"]:
                    arguments["evaluation_blocks"] = [
                        dict(
                            span=prior.span(body, "length = length + 1"),
                            learner_quote="changes only once",
                            text="Your reply counts one update total. In the earlier changed example there are two visits, Ada and Grace: starting2, the counter becomes3 then4. The final unindented print runs once after the body; printing inside would run on each visit.",
                        )
                    ]
            if not body["history"]:
                fault = second if "rejected_blocks" in body else first
                if fault == "format":
                    arguments["blocks"][0]["text"] = "x" * 901
                if fault == "span":
                    arguments["blocks"][0]["span"]["last_unit"] = 7999
                if fault is None:
                    jsonschema.validate(arguments, schema)
            else:
                jsonschema.validate(arguments, schema)
        return json.dumps(
            dict(
                id=f"authored-closeout-{index}",
                model="deepseek-flash",
                usage=dict(prompt_tokens=100, completion_tokens=60),
                choices=[
                    dict(
                        finish_reason="tool_calls",
                        message=dict(
                            tool_calls=[
                                dict(
                                    type="function", function=dict(name=name, arguments=json.dumps(arguments))
                                )
                            ]
                        ),
                    )
                ],
            )
        ).encode()

    summary = execute(output, mock_response=response)
    outcomes = json.loads((output / "outcomes.json").read_bytes())
    rows = json.loads((output / "runtime.json").read_bytes())["turns"]
    expected_sends = 4 if second else 8 if first else 7
    assert summary["sent_requests"] == expected_sends
    assert summary["real_model_calls"] == 0 and summary["cost_usd"] == "0"
    assert rows[0]["model_calls"] == (4 if first else 3)
    assert rows[0]["reserved_tokens"] <= 64000
    assert all(w["max_tokens"] == 4096 and w["parallel_tool_calls"] is False for w in observed)
    if first:
        assert [s["function"]["name"] for s in observed[3]["tools"]] == ["finish_tutor_turn"]
        journal = rows[0]["checkpoint"]["observations"]
        assert sum(o.get("error") == "TUTOR_FINISH_REPAIR_REQUIRED" for o in journal) == 1
    if second:
        assert [summary[k] for k in ("completed", "failed", "skipped")] == [0, 1, 2]
        assert outcomes[0]["error_code"] == "TUTOR_SHARED_FINISH_CORRECTION_INVALID"
        assert outcomes[0]["answer"] is None
    else:
        assert [summary[k] for k in ("completed", "failed", "skipped")] == [3, 0, 0]
        assert len(outcomes[0]["answer"]) == 2721
        assert all(t in outcomes[0]["answer"] for t in prior.teaching.LONG_BLOCKS)
        assert "Source: " not in outcomes[0]["answer"]
        assert "indented loop body" in outcomes[1]["answer"] and "final4" not in outcomes[1]["answer"]
        assert "two visits" in outcomes[2]["evaluation"] and "once after" in outcomes[2]["evaluation"]
        third = json.loads(observed[-1]["messages"][-1]["content"])
        assert third["history"][0]["answer"] == outcomes[0]["answer"]
        assert third["history"][1]["answer"] == outcomes[1]["answer"]
        assert all(len(t["answer"]) <= 4096 and len(t["evaluation"] or "") <= 1024 for t in outcomes)
