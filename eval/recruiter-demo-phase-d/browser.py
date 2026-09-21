"""Real Chromium acceptance: clean browser -> Java login -> real Agent -> saved work.
No mocked requests, token injection, precomputed model responses or retry-to-pass.
Every invocation writes a new private trial directory, including failures.
"""

import json
import re
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".data/recruiter-demo" / ("browser-" + uuid.uuid4().hex[:12])
OUT.mkdir(parents=True)
report = {"url": "http://127.0.0.1:5184/demo", "responses": [], "scenarios": [], "browser_errors": []}


def main():
    with sync_playwright() as p:
        installed = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
        browser = p.chromium.launch(
            executable_path=str(installed[-1]) if installed else None, headless=True, args=["--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: report["browser_errors"].append(str(error)))

        def response_seen(response):
            if "/study/command" in response.url:
                report["responses"].append(
                    {
                        "http": response.status,
                        "request": response.request.post_data_json,
                        "response": response.json(),
                    }
                )

        page.on("response", response_seen)
        try:
            page.goto(report["url"])
            page.screenshot(path=str(OUT / "entry.png"), full_page=True)
            page.get_by_role("button", name="进入 Sample Course", exact=True).click()
            expect(page.get_by_role("heading", name="学习助手", exact=True)).to_be_visible(timeout=20000)
            report["course_url"] = page.url
            task = page.url.split("/tasks/")[-1]
            token = page.evaluate("localStorage.getItem('courselingo.accessToken')")
            response = context.request.get(
                f"http://127.0.0.1:8084/api/tasks/{task}/evidence?limit=200",
                headers={"Authorization": "Bearer " + token},
            )
            assert response.ok
            evidence = {row["evidenceId"]: row for row in response.json()["data"]["items"]}
            report["evidence_count"] = len(evidence)

            def run_scenario(label, kind):
                page.get_by_role("button", name="新会话", exact=True).click()
                page.get_by_role("button", name=label, exact=True).click()
                started = time.monotonic()
                page.get_by_role("button", name="解释并出题", exact=True).click()
                expect(page.locator(".run-progress strong")).to_have_text(
                    re.compile("解释与练习已完成|课程证据不足|本次执行未完成|本次执行已达到时间或调用上限"),
                    timeout=130000,
                )
                reads = [
                    item["response"]["data"]
                    for item in report["responses"]
                    if item["request"]["operation"] == "READ" and item["response"].get("data", {}).get("run")
                ]
                result = reads[-1]
                row = {
                    "scenario": label,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "run_id": result["run"]["run_id"],
                    "session_id": result["run"]["session_id"],
                    "status": result["run"]["status"],
                    "kind": (result.get("artifact") or {}).get("kind", "practice"),
                }
                report["scenarios"].append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                assert result["run"]["status"] == "succeeded", result["run"].get("error_code")
                assert row["kind"] == kind
                assert result["run"]["model_mode"] == "real"
                if kind == "practice":
                    expect(page.locator(".practice-question")).to_have_count(2)
                    page.get_by_text("查看课程证据", exact=True).click()
                    ids = page.locator(".study-artifact .evidence-id").all_text_contents()
                    assert ids and set(ids) <= evidence.keys()
                    for citation in result["artifact"]["citations"]:
                        canonical = evidence[citation["evidence_id"]]
                        assert canonical["revision"] == result["artifact"]["revision"]
                        assert canonical["normalizedText"].startswith(citation["text"])
                    row["evidence_ids"] = ids
                    row["canonical_evidence_verified"] = True
                    page.locator(".study-artifact .citation button").first.click()
                    expected_seconds = result["artifact"]["citations"][0]["start_ms"] / 1000
                    page.wait_for_function(
                        "(t) => {const v=document.querySelector('video'); return v && v.readyState >= 2 && Math.abs(v.currentTime-t)<2}",
                        arg=expected_seconds,
                        timeout=20000,
                    )
                    row["video_seek_verified"] = True
                page.get_by_role("button", name="View Trace · 查看执行链路", exact=True).click()
                expect(page.locator(".run-trace")).to_contain_text("run_finished", timeout=10000)
                expect(page.locator(".run-trace")).to_contain_text("search_course_evidence")
                expect(page.locator(".run-trace")).to_contain_text("model_finished")
                row["trace_visible"] = True
                page.screenshot(path=str(OUT / f"scenario-{len(report['scenarios'])}.png"), full_page=True)
                return result

            first = run_scenario("1 · 解释概念与练习", "practice")
            page.get_by_label("第 1 题作答", exact=True).fill(
                "字符串不可变表示不能用索引赋值去改动原字符串中的字符；s = 'yello' 是让变量 s 重新绑定到另一个字符串，并没有把原字符串修改掉。"
            )
            page.locator(".practice-question").first.get_by_role(
                "button", name="保存作答", exact=True
            ).click()
            expect(page.locator(".practice-question").first).to_contain_text("已保存第 1 版", timeout=10000)
            page.locator(".practice-question").first.get_by_role(
                "button", name="获取证据反馈", exact=True
            ).click()
            expect(
                page.locator(".practice-question").first.get_by_role(
                    "heading", name="第 1 版作答的证据反馈", exact=True
                )
            ).to_be_visible(timeout=130000)
            report["feedback_saved"] = True
            page.screenshot(path=str(OUT / "feedback.png"), full_page=True)
            page.reload()
            expect(page.locator(".practice-question").first).to_contain_text("已保存第 1 版", timeout=20000)
            expect(page.get_by_role("heading", name="第 1 版作答的证据反馈", exact=True)).to_be_visible(
                timeout=20000
            )
            page.get_by_role("button", name="View Trace · 查看执行链路", exact=True).click()
            expect(page.locator(".run-trace")).to_contain_text("run_finished", timeout=10000)
            expect(page.locator(".run-trace")).to_contain_text(first["run"]["run_id"])
            report["reload_restores_answer_feedback_trace"] = True
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.screenshot(path=str(OUT / "mobile.png"), full_page=True)
            report["mobile_no_horizontal_overflow"] = True
            page.set_viewport_size({"width": 1440, "height": 1000})
            run_scenario("2 · 根据 Evidence 回答", "practice")
            run_scenario("3 · 课程外问题", "insufficient_evidence")
            expect(page.locator(".practice-question")).to_have_count(0)
            assert not report["browser_errors"]
            report["passed"] = True
        except Exception as error:
            report["passed"] = False
            report["failure"] = str(error)
            page.screenshot(path=str(OUT / "failure.png"), full_page=True)
            raise
        finally:
            path = OUT / "result.private.json"
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            path.chmod(0o600)
            print("Trial saved:", OUT, flush=True)
            browser.close()


if __name__ == "__main__":
    main()
