"""Authored E2E responses, not a product adapter or real quality evidence."""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch


def create_app():
    if (
        os.environ.get("AGENT_LLM_MODE") != "mock"
        or os.environ.get("TUTOR_ENGINE") != "light"
    ):
        raise RuntimeError("PHASE1D_MOCK_ONLY")
    from lecturelens_real_eval.tutor import light
    from lecturelens_real_eval.tutor.app import create_app as base

    class Authored:
        def complete(self, messages, schema, timeout):
            data = json.loads(messages[-1]["content"])
            question = data["learner_question"]
            eid = data["current_evidence"][0]["evidence_id"]
            focus = "最后一步" if "最后一步" in question else question[:40]
            if "无据问题" in question:
                result = {
                    "outcome": "insufficient_evidence",
                    "text": light.ABSTENTION,
                    "focus": "",
                }
            elif "摘录负例" in question:
                result = {
                    "outcome": "answered",
                    "text": data["current_evidence"][0]["text"] + f" [{eid}]",
                    "focus": "",
                }
            elif data["socratic"]:
                result = {
                    "outcome": "socratic_prompt",
                    "text": f"对于「{focus}」，你会在每项任务结束时还是全部结束后执行它？ [{eid}]",
                    "focus": focus,
                }
            elif data["dialogue"]:
                result = {
                    "outcome": "answered",
                    "text": f"沿用你先前设定的初值5和两项任务，每项增加一次，依次为5→6→7。若最后一步在全部任务结束后执行，就只观察最终状态7；课程的异步处理方法是依据，这些数值是学习者变式。 [{eid}]",
                    "focus": "",
                }
            else:
                result = {
                    "outcome": "answered",
                    "text": f"课程把提交与后台处理分开：提交后不用让浏览器一直等待，后台完成后再读取结果，这是异步流程。 [{eid}]\n你的变式以5为初值，两项任务各增加一次，因此5→6→7；它是方法应用而非课程原始数值。课程没有提供你所问的重试细节，这部分暂不能据此回答。 [{eid}]",
                    "focus": "",
                }
            result["usage"] = {"prompt_tokens": 100, "completion_tokens": 80}
            log = Path(os.environ["PHASE1D_REQUEST_LOG"])
            with log.open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "messages": messages,
                            "schema": schema,
                            "response": result,
                            "kind": "AUTHORED_MOCK",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            hold = Path(os.environ["TUTOR_MOCK_TEST_HOLD_DIR"])
            if (hold / "arm").exists():
                (hold / "entered").write_text(str(time.time_ns()) + "\n")
                end = time.monotonic() + 10
                while not (hold / "release").exists() and time.monotonic() < end:
                    time.sleep(0.05)
            return result

    app = base()
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        with patch.object(light, "MockLightTutor", Authored):
            async with original(app):
                yield

    app.router.lifespan_context = lifespan
    return app
