# LectureLens Agent Service — L1 dense retrieval

Python/FastAPI + 本地多语言 Embedding + PostgreSQL/pgvector。当前实现单课程证据检索，Java QA 可按配置调用；尚无 Agent Loop。

完整启动步骤、Java/Python 契约、验证与边界见 [L1 实施文档](../docs/L1_DENSE_RETRIEVAL.md)。

```bash
uv sync --locked
uv run --env-file ../.env.agent.local uvicorn lecturelens_agent.app:app --host 127.0.0.1 --port 8090
```

`/healthz` 在模型及数据库初始化后可用。业务端点只接受 Java 签名的当前证据快照，不接受浏览器用户自报身份。首次启动下载固定版本 ONNX 权重；服务运行期间没有付费 API 调用。

```bash
uv run ruff check src tests
uv run ruff format --check src tests
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent uv run pytest -q
```

测试使用确定性向量夹具；数据库相关用例使用真实 pgvector。未设置测试数据库地址时这部分用例会 skip，不能将其报告为完整通过。CI 提供真实数据库并执行全部用例。本地真实模型跨服务验证由 Java 的 `DenseRetrievalLiveIT` 单独执行。
