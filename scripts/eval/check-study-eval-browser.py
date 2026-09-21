#!/usr/bin/env python3
"""Check the latest real evaluation artifact in the UI; this is not a semantic quality test."""

import argparse
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--clip", default="strings")
    parser.add_argument("--output", type=Path, default=ROOT / ".data/l22-eval")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:5173")
    parser.add_argument("--report-prefix", default="final")
    args = parser.parse_args()
    assert args.report_prefix.replace("-", "").replace("_", "").isalnum()
    out = args.output
    auth_path = out / "courses" / args.clip / "session.local.json"
    auth = json.loads(auth_path.read_text())
    if auth.get("base_url", args.base_url.rstrip("/")) != args.base_url.rstrip("/"):
        raise ValueError("Course belongs to a different API endpoint")
    rows = [json.loads(line) for line in args.results.read_text().splitlines()]
    latest = [row for row in rows if row["case_id"].startswith(args.clip + "-")][-1]
    artifact = latest["artifact"]
    assert latest["run"]["status"] == "succeeded" and artifact
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/api/auth/login",
        data=json.dumps(auth["credentials"]).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        auth["token"] = json.loads(response.read())["data"]["accessToken"]
    auth_path.write_text(json.dumps(auth))
    expected_count = len(artifact["questions"])
    with sync_playwright() as playwright:
        installed = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
        browser = playwright.chromium.launch(
            executable_path=str(installed[-1]) if installed else None,
            headless=True,
            args=["--no-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.add_init_script(
            "localStorage.setItem('courselingo.accessToken', %s); localStorage.setItem('courselingo.userEmail', %s);"
            % (json.dumps(auth["token"]), json.dumps(auth["credentials"]["email"]))
        )
        page = context.new_page()
        page.goto(args.frontend_url.rstrip("/") + "/tasks/" + auth["task_id"])
        for reload in [False, True]:
            if reload:
                page.reload()
            page.get_by_role("button", name="学习助手", exact=True).click()
            expect(page.locator(".study-artifact")).to_be_visible(timeout=30000)
            expect(page.locator(".run-goal")).to_have_text(latest["run"]["goal"])
            expect(page.locator(".explanation")).to_have_text(artifact["explanation"])
            expect(page.locator(".practice-question")).to_have_count(expected_count)
            expect(page.locator(".answer")).to_have_count(0)
            if not expected_count:
                expect(page.get_by_role("button", name="查看参考答案与自查要点", exact=True)).to_have_count(0)
                expect(page.locator(".study-artifact details")).to_have_count(0)
        if expected_count:
            page.get_by_role("button", name="查看参考答案与自查要点", exact=True).click()
            expect(page.locator(".answer")).to_have_count(expected_count, timeout=15000)
        page.screenshot(path=str(out / f"{args.report_prefix}-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / f"{args.report_prefix}-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        browser.close()
    result = {
        "case_id": latest["case_id"],
        "artifact_kind": artifact["kind"],
        "restored_after_reload": True,
        "question_count": expected_count,
        "answers_hidden_until_requested": True,
        "empty_practice_controls_hidden": expected_count == 0,
        "mobile_no_horizontal_overflow": True,
        "semantic_quality_evaluated_here": False,
    }
    (out / f"{args.report_prefix}-browser-report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
