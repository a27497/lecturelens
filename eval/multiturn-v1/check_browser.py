"""Read back a recorded explanation through the isolated authenticated UI.

This checks rendering and persistence, never grades the explanation. Credentials,
records and screenshots must remain in ignored .data.
"""

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from run import ROOT, Gateway, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("auth", "record", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frontend-url", default="http://127.0.0.1:5176")
    args = parser.parse_args()
    if args.frontend_url != "http://127.0.0.1:5176":
        parser.error("Use the isolated frontend on port 5176")
    for path in (args.auth, args.record, args.output):
        if not path.resolve().is_relative_to(ROOT / ".data"):
            parser.error(
                "Private browser inputs and outputs must stay in ignored .data"
            )
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    auth, record = (json.loads(p.read_text()) for p in (args.auth, args.record))
    assert record["run"]["status"] == "succeeded"
    artifact = record["artifact"]
    assert artifact["kind"] == "explanation" and not artifact["questions"]
    gateway = Gateway(auth["base_url"])
    gateway.token = gateway.api("POST", "/api/auth/login", auth["credentials"])[
        "accessToken"
    ]
    errors = []
    with sync_playwright() as playwright:
        installed = sorted(
            (Path.home() / ".cache/ms-playwright").glob(
                "chromium-*/chrome-linux64/chrome"
            )
        )
        browser = playwright.chromium.launch(
            executable_path=str(installed[-1]) if installed else None,
            headless=True,
            args=["--no-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.add_init_script(
            "localStorage.setItem('courselingo.accessToken', {}); "
            "localStorage.setItem('courselingo.userEmail', {});".format(
                json.dumps(gateway.token), json.dumps(auth["credentials"]["email"])
            )
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.frontend_url + "/tasks/" + auth["task_id"])
        for reload in (False, True):
            if reload:
                page.reload()
            page.get_by_role("button", name="学习助手", exact=True).click()
            expect(page.get_by_label("学习目标", exact=True)).to_be_visible(
                timeout=30000
            )
            history = page.locator(".learning-history")
            expect(history).to_be_visible()
            if history.get_attribute("open") is None:
                history.locator("summary").click()
            selector = page.locator(".learning-history select")
            if selector.count():
                selector.select_option(record["run"]["session_id"])
            if history.get_attribute("open") is None:
                history.locator("summary").click()
            page.locator(".learning-history").get_by_role(
                "button", name=record["run"]["goal"], exact=True
            ).click()
            expect(page.locator(".explanation")).to_have_text(
                artifact["explanation"], timeout=30000
            )
            expect(page.locator(".run-progress strong")).to_have_text("课程解释已完成")
            expect(page.locator(".practice-question")).to_have_count(0)
            expect(
                page.get_by_role("button", name="查看参考答案与自查要点", exact=True)
            ).to_have_count(0)
            expect(
                page.get_by_role("button", name="开始学习", exact=True)
            ).to_be_enabled()
            expect(page.locator(".citation")).to_have_count(len(artifact["citations"]))
        page.locator(".study-artifact details summary").click()
        for citation in artifact["citations"]:
            expect(
                page.locator(".citation .evidence-id", has_text=citation["evidence_id"])
            ).to_be_visible()
        page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
        browser.close()
    assert not errors, errors
    report = {
        "restored_after_reload": True,
        "citation_count": len(artifact["citations"]),
        "empty_practice_controls_hidden": True,
        "explanation_status": True,
        "mobile_no_horizontal_overflow": True,
        "page_errors": 0,
        "semantic_quality_evaluated_here": False,
    }
    save(args.output / "report.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
