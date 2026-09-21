#!/usr/bin/env python3
"""Real browser + Java/Python/PG + local model management smoke. No cloud calls.

Requires the local stack on 8080/8090/5173 and llama.cpp alias lecturelens-local-qwen on 8091.
Creates two owned test accounts. Records their identities privately for scoped cleanup.
"""

import json
import os
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".data/model-management"


def main():
    os.umask(0o077)
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "browser-auth.json").exists(), "Do not overwrite an existing smoke cohort"
    accounts = []
    client = httpx.Client(base_url="http://127.0.0.1:8080", timeout=20, trust_env=False)
    for _ in range(2):
        credentials = {
            "email": f"models-{uuid.uuid4().hex}@example.test",
            "password": "Model!" + uuid.uuid4().hex,
        }
        response = client.post("/api/auth/register", json=credentials)
        assert response.status_code == 200, "Registration failed"
        response = client.post("/api/auth/login", json=credentials)
        assert response.status_code == 200, "Login failed"
        account = response.json()["data"]
        accounts.append(account)
        (OUT / "browser-auth.json").write_text(json.dumps(accounts))
    headers = {"Authorization": "Bearer " + accounts[0]["accessToken"]}
    other = {"Authorization": "Bearer " + accounts[1]["accessToken"]}

    def command(operation, **kwargs):
        response = client.post(
            "/api/agent/models/command", headers=headers, json={"operation": operation, **kwargs}
        )
        assert response.status_code == 200, f"Model operation {operation} failed with {response.status_code}"
        return response.json()["data"]

    assert command("LIST")["connections"] == []
    results = {
        "real_browser": True,
        "real_java_python_postgresql": True,
        "real_local_model": True,
        "paid_calls": False,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.add_init_script(
            "localStorage.setItem('courselingo.accessToken', "
            + json.dumps(accounts[0]["accessToken"])
            + ");localStorage.setItem('courselingo.userEmail','model-smoke@example.test');"
        )
        page = context.new_page()
        page.goto("http://127.0.0.1:5173/settings/models")
        page.get_by_role("heading", name="按任务选择模型").wait_for()
        page.get_by_label("连接名称", exact=True).fill("本地 Qwen · 决策")
        page.get_by_label("服务基础地址", exact=True).fill("http://127.0.0.1:8091/v1")
        page.get_by_label("API Key", exact=True).fill("local-smoke-test-key")
        page.get_by_role("button", name="保存连接", exact=True).click()
        page.get_by_text("连接已保存。可获取模型列表，或测试已填写的模型。", exact=True).wait_for()
        page.get_by_role("button", name="获取模型列表", exact=True).click()
        page.get_by_text("获取到", exact=False).wait_for()
        assert "lecturelens-local-qwen" in page.get_by_label("模型 ID（每行一个）", exact=True).input_value()
        page.get_by_role("button", name="保存连接", exact=True).click()
        page.get_by_text("连接已保存。可获取模型列表，或测试已填写的模型。", exact=True).wait_for()
        page.get_by_role("button", name="测试连接", exact=True).first.click()
        page.get_by_role("status").filter(has_text="工具调用测试通过").wait_for(timeout=20000)
        first = command("LIST")["connections"][0]
        results["first_probe"] = first["checks"]["lecturelens-local-qwen"]
        assert page.get_by_label("API Key", exact=True).input_value() == ""
        assert "local-smoke-test-key" not in page.locator("body").inner_text()

        page.get_by_role("button", name="＋ 新建", exact=True).click()
        page.get_by_label("连接名称", exact=True).fill("本地 Qwen · 复核")
        page.get_by_label("服务基础地址", exact=True).fill("http://127.0.0.1:8091/v1")
        page.get_by_label("模型 ID（每行一个）", exact=True).fill("lecturelens-local-qwen")
        page.get_by_role("button", name="保存连接", exact=True).click()
        page.get_by_text("连接已保存。可获取模型列表，或测试已填写的模型。", exact=True).wait_for()
        second = next(
            c for c in command("LIST")["connections"] if c["connection_id"] != first["connection_id"]
        )
        page.get_by_label("Agent 决策模型", exact=True).select_option(
            json.dumps([first["connection_id"], "lecturelens-local-qwen"], separators=(",", ":"))
        )
        page.get_by_label("草稿复核模型", exact=True).select_option(
            json.dumps([second["connection_id"], "lecturelens-local-qwen"], separators=(",", ":"))
        )
        page.get_by_role("button", name="保存模型用途", exact=True).click()
        page.get_by_text("模型用途已保存，将用于新创建的 Agent 运行。", exact=True).wait_for()
        page.reload()
        page.get_by_role("heading", name="按任务选择模型").wait_for()
        assert (
            json.loads(page.get_by_label("Agent 决策模型", exact=True).input_value())[0]
            == first["connection_id"]
        )
        assert (
            json.loads(page.get_by_label("草稿复核模型", exact=True).input_value())[0]
            == second["connection_id"]
        )
        results["bindings_restore_after_reload"] = True
        page.screenshot(path=str(OUT / "models-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUT / "models-mobile.png"), full_page=True)
        results["mobile_no_overflow"] = True
        browser.close()

    response = client.post("/api/agent/models/command", headers=other, json={"operation": "LIST"})
    assert response.status_code == 200 and response.json()["data"]["connections"] == []
    for operation in ["PROBE", "DELETE"]:
        response = client.post(
            "/api/agent/models/command",
            headers=other,
            json={
                "operation": operation,
                "connection_id": first["connection_id"],
                "version": first["version"],
                "model": "lecturelens-local-qwen",
            },
        )
        assert response.status_code == 404
    response = client.post(
        "/api/agent/models/command",
        headers=other,
        json={"operation": "LIST", "owner_id": accounts[0]["user"]["userId"]},
    )
    assert response.status_code == 400
    results["cross_account_access_rejected"] = True
    command("CLEAR_ROUTES")
    for connection in command("LIST")["connections"]:
        command("DELETE", connection_id=connection["connection_id"], version=connection["version"])
    assert command("LIST")["connections"] == []
    results["owned_connections_and_routes_deleted"] = True
    (OUT / "browser-result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
