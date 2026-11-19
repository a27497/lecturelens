"""Local fixture providers. Java remains the owner and Evidence authority."""
import json
import os
import re
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from lecturelens_agent.app import course_authority
from lecturelens_agent.study.errors import StudyError
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore
from lecturelens_real_eval.tutor.app import create_app as tutor_app
from lecturelens_real_eval.tutor.contracts import ABSTENTION
from lecturelens_real_eval.tutor.runtime import TutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore

from launch import COURSE, PACK

SEGMENTS = {segment["id"]: segment for segment in COURSE["segments"]}
ANSWERS = {turn["question"]: turn["answer"]
           for conversation in COURSE["conversations"] for turn in conversation["turns"]}
FOLLOWUPS = {
    "如果目标比中点小，应该移动哪个边界？": [("s06", "把右边界移到中点的前一格。本例比较到 42 时，目标 34 更小，因此 42 和右边所有值都能排除。")],
    "如果一直没找到，什么时候停止？": [("s09", "当左边界超过右边界，搜索区间已经空了，就可以停止并报告未找到。")],
    "数组没有排序时，还能排除左半边吗？": [("s01", "不能。有序性让我们知道左边每个值都不超过中点；打乱后，目标可能在左右任何一侧。")],
}


def state():
    return json.loads(Path(os.environ["ROUND3_DEMO_STATE"]).read_text())


def demo_scope(scope):
    bound = state()
    return scope["course_id"] == bound.get("task_id") and str(scope["owner_id"]) == bound.get("round3_owner")


def segment_evidence(authority, scope, segment_id):
    segment = SEGMENTS[segment_id]
    rows = authority.read(
        scope, "SEARCH", query=segment["source"],
        start_ms=segment["startMs"], end_ms=segment["endMs"] - 1,
    )["evidence"]
    row = next((row for row in rows if row["source_type"] == "SUBTITLE"
                and row["start_ms"] == segment["startMs"] and row["end_ms"] == segment["endMs"]
                and normalized(row["text"]) == normalized(segment["source"])), None)
    return row


class FixtureTutorAuthority:
    def __init__(self, authority):
        self.authority = authority

    def read(self, scope, action="CHECK", **arguments):
        query = arguments.get("query", "")
        ids = query.removeprefix("round3:").split(",")
        if action == "SEARCH" and query.startswith("round3:") and demo_scope(scope) and all(id in SEGMENTS for id in ids):
            found = [segment_evidence(self.authority, scope, id) for id in dict.fromkeys(ids)]
            return self.authority.read(scope, "READ", evidence_ids=[row["evidence_id"] for row in found if row])
        return self.authority.read(scope, action, **arguments)


class FixtureTutor:
    mode = "mock"

    def decide(self, messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        question = data["learner_text"].strip()
        question = re.sub(r"^关于\s+\d+:\d+\s+这段[：:]\s*", "", question)
        blocks = ANSWERS.get(question)
        if blocks is None and question in FOLLOWUPS:
            blocks = [{"concept": "", "text": text, "citations": [id]} for id, text in FOLLOWUPS[question]]
        if not data["observations"]:
            ids = list(dict.fromkeys(id for block in blocks or [] for id in block["citations"]))
            return {"name": "search_tutor_evidence", "arguments": {"query": "round3:" + ",".join(ids) if ids else question}}
        by_segment = {id: row["evidence_id"] for id, segment in SEGMENTS.items() for row in data["evidence"]
                      if row["source_type"] == "SUBTITLE" and row["start_ms"] == segment["startMs"]
                      and row["end_ms"] == segment["endMs"] and normalized(row["text"]) == normalized(segment["source"])}
        if not blocks or any(id not in by_segment for block in blocks for id in block["citations"]):
            arguments = {"outcome": "insufficient_evidence", "text": ABSTENTION}
        else:
            text = "\n\n".join(
                (block["concept"] + "\n" if block["concept"] else "") + block["text"]
                + "".join(f" [{by_segment[id]}]" for id in block["citations"]) for block in blocks
            )
            evaluation = ""
            if data["history"] and data["history"][-1]["outcome"] == "socratic_prompt":
                evaluation = f"把你的边界更新和课程里的这一步对照看看。 [{next(iter(by_segment.values()))}]"
            if data["socratic"]:
                text = f"看一下这一段的比较结果。你会保留中点的哪一侧，为什么？ [{next(iter(by_segment.values()))}]"
            arguments = {"outcome": "socratic_prompt" if data["socratic"] else "answered",
                         "text": text, "evaluation": evaluation}
        return {"name": "finish_tutor_turn", "arguments": arguments}


class PracticeState(TypedDict):
    run_id: str
    done: bool


class FixtureStudy(StudyRuntime):
    def graph(self, run, token, saver, provider=None):
        if not demo_scope(run) or run["request_key"] != "round3-practice" or run["practice_format"] != "choice":
            return super().graph(run, token, saver, provider)

        def publish(_):
            ids = list(dict.fromkeys(id for exercise in COURSE["exercises"] for id in exercise["citations"]))
            sources = {id: segment_evidence(self.authority, run, id) for id in ids}
            if any(row is None for row in sources.values()):
                raise StudyError("ROUND3_FIXTURE_EVIDENCE_MISSING")
            citations = self.authority.read(run, "READ", evidence_ids=[row["evidence_id"] for row in sources.values()])["evidence"]
            questions = [{
                "kind": "choice", "question": exercise["prompt"],
                "options": exercise["options"], "correct_option_id": exercise["correctOptionId"],
                "evidence_ids": [sources[id]["evidence_id"] for id in exercise["citations"]],
            } for exercise in COURSE["exercises"]]
            self.store.guard(run["run_id"], token)
            self.store.reserve(run["run_id"], token, "tool", key="round3")
            self.store.save_tool(run["run_id"], token, "round3", "load_demo_practice", {}, {}, artifact={
                "kind": "practice", "title": "二分查找练习", "explanation": "用新的例子练习更新边界和判断停止条件。",
                "questions": questions, "citations": citations, "revision": run["revision"],
                "evidence_ids": [row["evidence_id"] for row in citations], "mode": "mock",
            })
            return {"done": True}

        builder = StateGraph(PracticeState)
        builder.add_node("publish", publish)
        builder.add_edge(START, "publish")
        builder.add_edge("publish", END)
        return builder.compile(checkpointer=saver)


def normalized(text):
    return " ".join(text.casefold().split())


def java_fixture(body):
    messages = [message["content"] for message in body["messages"]]
    for message in messages:
        if "Input JSON:" in message and "sourceSegmentIndex" in message:
            source = json.loads(message.split("Input JSON:", 1)[1])["segments"]
            by_text = {normalized(segment["source"]): segment["translation"] for segment in SEGMENTS.values()}
            if not all(normalized(row["text"]) in by_text for row in source):
                raise HTTPException(422, "No translation in the demo material")
            return {"segments": [{"index": row["index"], "text": by_text[normalized(row["text"])]} for row in source]}
    if "输出 JSON object，字段为 chapters" in messages[0]:
        bounds = [(int(i), int(start), int(end)) for i, start, end in re.findall(r"(?m)^\[(\d+)\].*? start=(\d+) end=(\d+)", "\n".join(messages))]
        return {"chapters": [
            {"title": chapter["title"], "summary": " ".join(s["translation"] for s in SEGMENTS.values() if s["chapterId"] == chapter["id"]),
             "startTimeMillis": chapter["startMs"], "endTimeMillis": chapter["endMs"],
             "keywords": [], "evidenceIndexes": [i for i, start, end in bounds if start < chapter["endMs"] and end > chapter["startMs"]]}
            for chapter in COURSE["chapters"]
        ]}
    if '"citedEvidenceIndexes"' in "\n".join(messages):
        return {"answer": "这一段讲解如何利用有序数据缩小搜索区间。", "citedEvidenceIndexes": [0]}
    if any("binary search needs sorted data" in normalized(m) or "二分查找需要有序数据" in m for m in messages):
        return {
            "summary": COURSE["description"] + " 已排序的数组允许排除不可能含目标的半边。",
            "keyPoints": ["二分查找要求数据有序。", "中点偏小，左边界移动到中点后一格。", "左边界超过右边界时结束。"],
            "glossary": [{"term": "搜索区间", "definition": "仍可能包含目标的下标范围。"},
                         {"term": "中点", "definition": "每一轮先和目标进行比较的位置。"}],
            "qa": [{"question": "为什么要跳过中点？", "answer": "它已经比较过，确认不等于目标。"}],
        }
    raise HTTPException(422, "No response in the demo material")


def create_app():
    if os.environ.get("AGENT_LLM_MODE") != "mock":
        raise RuntimeError("Round 3 uses local fixtures")
    java = os.environ["AGENT_JAVA_BASE_URL"]
    dsn = os.environ["AGENT_DATABASE_URL"]
    secret = os.environ["AGENT_SERVICE_SECRET"]
    app = tutor_app(
        tutor=TutorRuntime(TutorStore(dsn), FixtureTutorAuthority(course_authority(java, secret)), FixtureTutor()),
        study_runtime=FixtureStudy(StudyStore(dsn), course_authority(java, secret), MockProvider(), concurrency=1),
    )

    @app.post("/v1/chat/completions")
    async def completions(request: Request):
        if request.headers.get("authorization") != "Bearer local-round3-fixture":
            raise HTTPException(401)
        answer = java_fixture(await request.json())
        return {"model": "round3-fixture", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    @app.post("/api/round3/entry")
    async def entry(request: Request):
        if (request.headers.get("origin") != os.environ["ROUND3_DEMO_ORIGIN"]
                or request.headers.get("sec-fetch-site") != "same-origin"):
            raise HTTPException(403)
        bound = state()
        if not bound.get("round3_practice"):
            raise HTTPException(503)
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            response = await client.post(java + "/api/auth/login", json={
                "email": os.environ["ROUND3_DEMO_EMAIL"], "password": os.environ["ROUND3_DEMO_PASSWORD"],
            })
        session = response.json()
        if response.status_code != 200 or str(session.get("code")) != "0":
            raise HTTPException(503)
        return JSONResponse(session["data"], headers={"Cache-Control": "no-store"})

    @app.get("/api/round3/course")
    async def metadata(request: Request):
        bound = state()
        authorization = request.headers.get("authorization", "")
        task_id = bound.get("task_id")
        if not authorization or not task_id or not bound.get("round3_practice"):
            raise HTTPException(404)
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            response = await client.get(java + f"/api/tasks/{task_id}", headers={"Authorization": authorization})
        if response.status_code != 200 or str(response.json().get("code")) != "0":
            raise HTTPException(404)
        return JSONResponse({
            "taskId": task_id, "title": COURSE["title"], "series": COURSE["series"],
            "description": COURSE["description"], "durationMs": COURSE["durationMs"],
            "positionMs": COURSE["progress"]["positionMs"], "cover": "/api/round3/cover",
            "notes": [{"id": note["id"], "text": note["title"] + "\n" + note["body"],
                       "anchor": {"kind": "playback", "milliseconds": SEGMENTS[note["anchor"]]["startMs"]}}
                      for note in COURSE["notes"]],
            "followups": list(FOLLOWUPS),
            "topics": [{ "question": conversation["turns"][0]["question"], "title": conversation["title"] }
                       for conversation in COURSE["conversations"]],
        }, headers={"Cache-Control": "no-store"})

    @app.get("/api/round3/cover")
    async def cover():
        return FileResponse(PACK / COURSE["cover"], media_type="image/png")

    @app.get("/api/round3/practice/{artifact_id}/{index}")
    async def explanation(artifact_id: str, index: int, request: Request):
        bound = state()
        practice = bound.get("round3_practice", {})
        authorization = request.headers.get("authorization", "")
        if not authorization or practice.get("artifact_id") != artifact_id or not 0 <= index < len(COURSE["exercises"]):
            raise HTTPException(404)
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            response = await client.post(java + f"/api/tasks/{bound['task_id']}/study/command",
                                         headers={"Authorization": authorization}, json={
                    "operation": "READ", "session_id": practice["session_id"], "run_id": practice["run_id"],
                })
        if response.status_code != 200 or str(response.json().get("code")) != "0":
            raise HTTPException(404)
        if not any(attempt["question_index"] == index for attempt in response.json()["data"]["attempts"]):
            raise HTTPException(404)
        return JSONResponse({"explanation": COURSE["exercises"][index]["explanation"]},
                            headers={"Cache-Control": "no-store"})

    return app
