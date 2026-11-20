"""Local fixture providers. Java remains the owner and Evidence authority."""
import asyncio
import hmac
import json
import logging
import os
import re
import secrets
import time

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

from launch import COURSE, INSTANCE, PACK, Round3Stack

SEGMENTS = {segment["id"]: segment for segment in COURSE["segments"]}
ANSWERS = {turn["question"]: turn["answer"]
           for conversation in COURSE["conversations"] for turn in conversation["turns"]}
FOLLOWUPS = {
    "如果目标比中点小，应该移动哪个边界？": [("s06", "把右边界移到中点的前一格。本例比较到 42 时，目标 34 更小，因此 42 和右边所有值都能排除。")],
    "如果一直没找到，什么时候停止？": [("s09", "当左边界超过右边界，搜索区间已经空了，就可以停止并报告未找到。")],
    "数组没有排序时，还能排除左半边吗？": [("s01", "不能。有序性让我们知道左边每个值都不超过中点；打乱后，目标可能在左右任何一侧。")],
}
TOPICS = [(re.compile(topic["match"], re.I), topic)
          for topic in COURSE["tutorQuestions"] + COURSE["tutorFollowups"]]
ANSWERS.update({topic["question"]: topic["answer"] for _, topic in TOPICS})
ANSWERS.update({
    question: [{"concept": "", "text": text, "citations": [segment]} for segment, text in blocks]
    for question, blocks in FOLLOWUPS.items()
})
OTHER_ALGORITHMS = re.compile(r"堆排序|快速排序|归并排序|冒泡排序|插入排序|图论|最短路径|拓扑排序|dijkstra", re.I)
GUIDANCE_REQUEST = re.compile(r"没跟上|看不懂|没懂|不明白|不太懂|从哪|先看|怎么想|怎么理解|怎么做|理清|梳理|有点[晕懵]")
LESSON_CONTEXT = re.compile(r"这[段节块课]|本课|课[上里]|搜索区间|候选区间|二分(?:查找|搜索)|折半查找|binary search", re.I)
COURSE_GUIDANCE = [
    (r"边界|指针|端点|搜索区间|候选区间|(?<![a-z0-9_])(?:low|high)(?![a-z0-9_])",
     "先看中点与目标的比较结果，决定哪一边还能保留。每次更新后，再看区间里还有几个候选。你想先弄清怎么移动边界，还是怎么判断是否结束？",
     ["s04", "s09"]),
    (r"中点|中间(?:项|值|下标|位置)|(?<![a-z0-9_])mid(?![a-z0-9_])",
     "先用左右边界算出中点下标，再取这个位置的值与目标比较。你想先看怎么算下标，还是比较后往哪一边找？",
     ["s03", "s04"]),
    (r"二分(?:查找|搜索)|折半查找|binary search|(?:这节课|本课)(?:我|的内容)?(?:有点|都)?(?:没跟上|看不懂|没懂|不明白)",
     "先暂停在例题第一次比较。中点是 21，目标是 34。试着判断 21 的哪一侧还可能有 34，我们再从这一步往下走。",
     ["s05"]),
]


def answer_blocks(question):
    question = re.sub(r"^关于\s+\d+:\d+\s+这段[：:]\s*", "", question.strip())
    if question in ANSWERS:
        return ANSWERS[question]

    clauses = re.split(r"[？?；;\n]+|[，,]\s*(?:另外|以及|还有|那|再问)", question)
    matches = [{index for index, (pattern, _) in enumerate(TOPICS)
                if not OTHER_ALGORITHMS.search(clause) and pattern.search(clause)}
               for clause in clauses if clause.strip()]
    selected = set().union(*matches)
    blocks = [block for index, (_, topic) in enumerate(TOPICS) if index in selected
              for block in topic["answer"]]
    if (not blocks and GUIDANCE_REQUEST.search(question) and LESSON_CONTEXT.search(question)
            and not OTHER_ALGORITHMS.search(question)):
        for pattern, text, citations in COURSE_GUIDANCE:
            if re.search(pattern, question, re.I):
                return [{"concept": "从课里的这一步看", "text": text, "citations": citations}]
    if blocks and any(not topics for topics in matches):
        blocks.append({"concept": "", "text": "其余部分在本课中没有找到足够的依据。", "citations": []})
    return blocks


class Visitors:
    def __init__(self):
        self.stack = Round3Stack(INSTANCE)
        self.directory = self.stack.dir / "visitors"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.pending = None
        self.claim = asyncio.Lock()

    def binding(self, owner):
        if not str(owner).isdecimal():
            return {}
        try:
            return json.loads((self.directory / f"{owner}.json").read_text())
        except FileNotFoundError:
            return {}

    def provision(self):
        credentials = {"email": f"round3-{secrets.token_hex(12)}@example.com", "password": "a1" + secrets.token_urlsafe(32)}
        self.stack.api("POST", "/api/auth/register", credentials)
        account = self.stack.api("POST", "/api/auth/login", credentials)
        token = account["accessToken"]
        binding_file = self.directory / f"{account['user']['userId']}.json"

        def save_binding(binding):
            temporary = binding_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(binding))
            temporary.replace(binding_file)

        try:
            task = self.stack.import_course(token, lambda task: save_binding({"task_id": task}))
        except SystemExit as error:
            raise RuntimeError("Round 3 course preparation failed") from error
        tutor = f"/api/tasks/{task}/tutor/sessions"
        conversation_paths = []
        for conversation in reversed(COURSE["conversations"]):
            session = self.stack.api("POST", tutor, {"request_key": "round3-" + conversation["id"]}, token)["session"]
            session_path = f"{tutor}/{session['session_id']}"
            conversation_paths.append(session_path)
            for index, turn in enumerate(conversation["turns"]):
                self.stack.api("POST", f"{session_path}/turns", {
                    "client_turn_id": f"round3-{conversation['id']}-{index}",
                    "text": turn["question"], "socratic": False,
                }, token)

        path = f"/api/tasks/{task}/study/command"
        session = self.stack.api("POST", path, {"operation": "CREATE_SESSION", "request_key": "round3-practice"}, token)
        scope = {"session_id": session["session_id"]}
        response = self.stack.api("POST", path, {
            **scope, "operation": "START", "request_key": "round3-practice",
            "goal": "复习二分查找", "practice_format": "choice",
        }, token)
        run = response["run"]["run_id"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = self.stack.api("POST", path, {**scope, "operation": "READ", "run_id": run}, token)
            status = response["run"]["status"]
            turns = [turn for session_path in conversation_paths
                     for turn in self.stack.api("GET", session_path, token=token)["turns"]]
            if status == "succeeded" and all(turn["outcome"] == "answered" for turn in turns):
                save_binding({"task_id": task, "practice": {**scope, "run_id": run,
                              "artifact_id": response["artifact"]["artifact_id"]}})
                return credentials
            if status not in {"queued", "running", "succeeded"} or any(
                turn["status"] in {"failed", "cancelled"} or turn["outcome"] == "insufficient_evidence" for turn in turns
            ):
                raise RuntimeError("Round 3 learning fixture failed")
            time.sleep(.5)
        raise RuntimeError("Round 3 learning fixture timed out")

    async def provision_or_log(self):
        try:
            return await asyncio.to_thread(self.provision)
        except Exception as error:
            logging.getLogger(__name__).error("Round 3 visitor preparation failed (%s)", type(error).__name__)
            return None

    async def ready(self):
        if self.pending is None:
            self.pending = asyncio.create_task(self.provision_or_log())
        credentials = await asyncio.shield(self.pending)
        if credentials is None:
            self.pending = None
            raise HTTPException(503)
        return credentials

    async def enter(self):
        # Consume each prepared account once. Keep one ready for the next browser.
        async with self.claim:
            credentials = await self.ready()
            try:
                account = await asyncio.to_thread(self.stack.api, "POST", "/api/auth/login", credentials)
            except RuntimeError:
                raise HTTPException(503) from None
            self.pending = asyncio.create_task(self.provision_or_log())
            return account

    def owns_fixture(self, scope):
        return scope["course_id"] == self.binding(scope["owner_id"]).get("task_id")


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
    def __init__(self, authority, visitors):
        self.authority = authority
        self.visitors = visitors

    def read(self, scope, action="CHECK", **arguments):
        query = arguments.get("query", "")
        suffix = query.removeprefix("round3:")
        ids = suffix.split(",") if suffix else []
        if action == "SEARCH" and query.startswith("round3:") and self.visitors.owns_fixture(scope) and all(id in SEGMENTS for id in ids):
            found = [segment_evidence(self.authority, scope, id) for id in dict.fromkeys(ids)]
            return self.authority.read(scope, "READ", evidence_ids=[row["evidence_id"] for row in found if row])
        return self.authority.read(scope, action, **arguments)


class FixtureTutor:
    mode = "mock"

    def decide(self, messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        blocks = answer_blocks(data["learner_text"])
        if not blocks and data["history"] and re.fullmatch(
            r"(?:那[，, ]*)?(?:为什么呢|能不能再解释一下|可以再讲一遍吗|刚才那点能再详细讲讲吗)[？?。 ]*",
            data["learner_text"].strip(),
        ):
            blocks = answer_blocks(data["history"][-1]["learner_text"])
        ids = list(dict.fromkeys(id for block in blocks for id in block["citations"]))
        # The Tutor runtime exposes eight evidence rows per search.
        batches = [ids[index:index + 8] for index in range(0, len(ids), 8)] or [[]]
        searched = len(data["observations"])
        if searched < len(batches):
            return {"name": "search_tutor_evidence", "arguments": {"query": "round3:" + ",".join(batches[searched])}}
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
    def __init__(self, store, authority, visitors):
        super().__init__(store, authority, MockProvider(), concurrency=1)
        self.visitors = visitors

    def graph(self, run, token, saver, provider=None):
        if not self.visitors.owns_fixture(run) or run["request_key"] != "round3-practice" or run["practice_format"] != "choice":
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
    visitors = Visitors()
    authority = course_authority(java, secret)
    app = tutor_app(
        tutor=TutorRuntime(TutorStore(dsn), FixtureTutorAuthority(authority, visitors), FixtureTutor()),
        study_runtime=FixtureStudy(StudyStore(dsn), authority, visitors),
    )

    @app.post("/v1/chat/completions")
    async def completions(request: Request):
        if request.headers.get("authorization") != "Bearer local-round3-fixture":
            raise HTTPException(401)
        answer = java_fixture(await request.json())
        return {"model": "round3-fixture", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    @app.post("/api/round3/ready")
    async def ready(request: Request):
        if not hmac.compare_digest(request.headers.get("x-round3-secret", "").encode(), secret.encode()):
            raise HTTPException(403)
        async with visitors.claim:
            await visitors.ready()
        return {"ready": True}

    @app.post("/api/round3/entry")
    async def entry(request: Request):
        if (request.headers.get("origin") != os.environ["ROUND3_DEMO_ORIGIN"]
                or request.headers.get("sec-fetch-site") != "same-origin"):
            raise HTTPException(403)
        return JSONResponse(await visitors.enter(), headers={"Cache-Control": "no-store"})

    async def authorized_binding(request):
        authorization = request.headers.get("authorization", "")
        if not authorization:
            raise HTTPException(404)
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            response = await client.get(java + "/api/me", headers={"Authorization": authorization})
            if response.status_code != 200 or str(response.json().get("code")) != "0":
                raise HTTPException(404)
            bound = visitors.binding(response.json()["data"]["userId"])
            if not bound.get("practice"):
                raise HTTPException(404)
            response = await client.get(java + f"/api/tasks/{bound['task_id']}", headers={"Authorization": authorization})
        if response.status_code != 200 or str(response.json().get("code")) != "0":
            raise HTTPException(404)
        return bound

    @app.get("/api/round3/course")
    async def metadata(request: Request):
        bound = await authorized_binding(request)
        return JSONResponse({
            "taskId": bound["task_id"], "title": COURSE["title"], "series": COURSE["series"],
            "description": COURSE["description"], "durationMs": COURSE["durationMs"],
            "positionMs": COURSE["progress"]["positionMs"], "learningPercent": COURSE["progress"]["percent"],
            "cover": "/api/round3/cover",
            "notes": [{"id": note["id"], "text": note["title"] + "\n" + note["body"],
                       "anchor": {"kind": "playback", "milliseconds": SEGMENTS[note["anchor"]]["startMs"]}}
                      for note in COURSE["notes"]],
            "followups": list(FOLLOWUPS),
            "questions": [topic["question"] for topic in COURSE["tutorQuestions"]],
            "topics": [{ "question": conversation["turns"][0]["question"], "title": conversation["title"] }
                       for conversation in COURSE["conversations"]],
        }, headers={"Cache-Control": "no-store"})

    @app.get("/api/round3/cover")
    async def cover():
        return FileResponse(PACK / COURSE["cover"], media_type="image/png")

    @app.get("/api/round3/practice/{artifact_id}/{index}")
    async def explanation(artifact_id: str, index: int, request: Request):
        bound = await authorized_binding(request)
        practice = bound["practice"]
        authorization = request.headers["authorization"]
        if practice["artifact_id"] != artifact_id or not 0 <= index < len(COURSE["exercises"]):
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
