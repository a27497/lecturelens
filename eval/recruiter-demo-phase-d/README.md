# Phase D：Recruiter Demo

本机入口：**http://127.0.0.1:5184/demo**。用户选择隔离本机交付；没有发布公网服务，也没有修改原线上 8080/8090/8091。

这是现有能力的演示包装：Vue → 原 Java 登录/Study 网关 → 原 Python Study runtime → 原 Evidence Authority。未新增 Agent 工具、prompt、执行状态、权限例外或数据库写入通道。MCP 保留 Phase C 成果，演示默认仍用 `internal`，不抢主线。

## Sample Course

- Ana Bell，MIT OpenCourseWare，6.0001 Fall 2016，Lecture 3 的 **11:00–12:57** 字符串片段。
- [原课程](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-3-string-manipulation-guess-and-check-approximations-bisection/)，[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。使用原公开视频和字幕，剪辑、重编码、字幕时轴平移并嵌入；中文翻译由模型生成。来源/hash 清单沿用 [sources.json](../study-v1/sources.json)。此处供本机非商业展示，署名及许可仍适用。
- 独立演示账号，独立课程 `task_9530f04391b94c84b1ffc6a49228cecc`，revision **2**，索引 **READY**。
- 片段 SHA256：`912abfda246ad20d6f35b1c9ef4237bd0f8a68eac3fe871563584f735770f342`。
- 维护者已通过现有 register/login/upload/task/index 流程准备完毕。访客只需点击「进入 Sample Course」，不上传、不配置模型、不注入 token。
- 专用账号是共享演示身份，正常经过 Java 登录/ownership 检查；访客可看到该账号的合成作答，也拥有原业务允许的账号操作权限。勿输入私人资料，勿将普通账号凭据用于演示配置。A/B/C 原课程和评测账号均未改动。

## 五个场景 / 面试操作脚本（约 3–5 分钟）

1. 打开 `/demo`，点击 **进入 Sample Course**。说明“这是公开课程的已准备片段，真实模型根据 Evidence 工作”。点击 **1 · 解释概念与练习** → **解释并出题**。观察查找证据、模型复核和解释结果。不要把生成练习描述成自动评分。
2. 展开 **查看课程证据**。指向一条完整 Evidence ID、原文和时间，点击 **跳到视频**。展示“字符串不能索引赋值，但变量可以重新绑定”的来源。还可选择 **2 · 根据 Evidence 回答** → **解释并出题**，演示对具体课程问题的回答；这仍是原 Study Agent 的解释加练习任务。
3. 点击 **新会话**，选择 **3 · 课程外问题** → **解释并出题**。问题要求 Kubernetes 节点数量和部署步骤；预期显示课程证据不足，不编造部署答案、不生成无据习题。实际模型失败会显示原终态，可查看 Trace；不要把失败说成正确拒答。
4. 回到课程内那次 **最近学习记录**，第一题输入自己的理解 → **保存作答** → **获取证据反馈**。查看反馈引用、精确作答版本；刷新仍可恢复。可展开参考答案自查，反馈核对入口保留。
5. 点击 **View Trace · 查看执行链路**。检查 Run ID、模型、调用数、持久化事件、工具名称、实际 token/模型延迟、Evidence IDs 和最终回答。历史 Run 同样可看。事件序号可能跳号；这是私有诊断事件被过滤后的原游标，不是数据丢失。

页面 Trace 是已有 `EVENTS` 接口的公开投影，不暴露私有模型请求、完整工具结果/参考答案或 checkpoint 内容。完整诊断与 Replay 继续使用 [Phase B CLI](../agent-trace-phase-b/README.md)，需要数据库运维权限和 Java 当前授权。网页没有增加 Trace API。未知 token 不估算，工具时延没有在公开事件中时不伪造。

模型失败时：先保留 Run 和 Trace；可从“最近学习记录”选择本次验收的成功 Run 演示持久化结果，并明确这是已保存结果。完整 Run ID、真实失败和测试见 [results.json](results.json)，原始响应和浏览器截图在忽略的 `.data/recruiter-demo/`，不进入 Git。

## 本次验收结果（2026-09-21）

真实 Chromium 从空白上下文正常登录，五个场景全部通过；未 mock HTTP、注入 token 或替换模型回答。模型为 qwen3-max。

| 场景 | 浏览器端到端耗时 | 模型 / 工具调用 | 实际输入 / 输出 token | 结果 |
| --- | ---: | ---: | ---: | --- |
| 解释概念并出题 | 19.951 s | 5 / 4 | 11,970 / 678 | 成功；一次草稿复核拒绝后修订 |
| 具体 Evidence 问题 | 15.930 s | 3 / 2 | 6,439 / 498 | 成功；6 条真实 Evidence |
| Kubernetes 课程外问题 | 10.896 s | 4 / 2 | 5,768 / 309 | 证据不足拒答；0 道题 |
| 保存回答、证据反馈 | 另一个 feedback Run | 4 / 2 | 此表不汇总 | guidance，精确关联第 1 版作答 |
| 历史 Trace | 原 EVENTS 读取 | 无新增模型调用 | 不产生 token | 刷新后可恢复 |

解释 Run `36ca6bcc-582e-4188-b66c-766788904c2b`；反馈 Run `6c5c4f71-5e0d-485a-b1c1-8ca612f376e7`。说明、具体问题和拒答的全量 ID 及指标保存在 `results.json`。原字幕与反馈已经 AI 来源复核；没有独立人工评分，也不构成新的质量 Benchmark。

浏览器还通过 390px 无横向溢出、作答/反馈/Trace 刷新恢复、历史会话选择，以及真实视频就绪与证据跳转（17.59s）。页内无 JavaScript 错误。最后只读复查确认 Trace 显示 provider 返回的 `prompt_tokens` / `completion_tokens`，没有将预留预算当实际 token。

首次 browser trial 在“刷新恢复”断言处失败：误以为 `run_finished` 必须是最后事件，但已保存作答会合法追加 `attempt_saved`。保留首次真实出题、反馈、响应及失败截图；只修正验收脚本的事件存在性断言，未改变产品逻辑，第二个完整 trial 通过。另保留模型草稿的复核拒绝事件，不将其从 Trace 删除。

回归：**Python/PostgreSQL 605 passed、0 skipped；前端 85 passed；Java 相关 62 passed、0 skipped；生产构建、Ruff 和 diff whitespace 检查通过**。全量 Python 包含恢复、取消、幂等、权限、revision、deletion、stale-result isolation，以及 A/B/C 机制测试。构建仅有既有第三方 PURE 注解、bundle 大小提醒；Python 有 Starlette/AnyIO 弃用提醒。无新增 Java/Agent runtime 修改。

**Phase D 完成。求职版开发到此停止，不开启新 Phase。** 本机演示保持运行；原线上服务仍保持原配置。

## 启动 / 复现

已启动时直接访问入口。当前机器使用既有隔离 MySQL、PostgreSQL、Redis、MinIO、RocketMQ 和私有运行配置；`serve.py` 不安装或修改这些依赖，不把线上配置复制成演示。重启前停止本轮占用 8084/8094/5184 的演示进程，保留线上进程。

```bash
# 仓库根目录；隔离基础服务需要先运行（见 docs/DEPLOYMENT.md）。
docker start lecturelens-loop-redis
uv sync --directory agent-service --frozen
npm --prefix frontend ci
(cd backend && ./mvnw -q -DskipTests package)

# 分别在三个终端中执行；Ctrl-C 停止各组件。
python3 eval/recruiter-demo-phase-d/serve.py backend
python3 eval/recruiter-demo-phase-d/serve.py agent
python3 eval/recruiter-demo-phase-d/serve.py frontend
```

默认读取 `.data/phase-completion-20260920/runtime.local.json`（隔离 Java 8084、MySQL `lecturelens_learning_loop`、独立 Agent PG、真实模型环境）和 `.data/recruiter-demo/session.local.json`。可用 `--runtime`、`--session`、`--jar` 指定本机路径。运行配置模板见 `.env.agent.example` 与部署文档；本机私有配置和已准备课程不是可提交资源。新机器需要先完成服务配置与维护者播种，不宣称全新机器零配置启动。

如果还没有专用账号/课程，在 Java/Agent 启动后、frontend 启动前运行一次；使用**新的** output 目录保留旧账号与失败试次：

```bash
python3 scripts/eval/prepare-study-courses.py  # 已有 hash 匹配的公开片段可跳过下载准备
python3 scripts/eval/accept-study-agent.py --phase prepare \
  --base-url http://127.0.0.1:8084 --output .data/recruiter-demo \
  --video .data/l22-eval/sources/strings.mp4
```

`serve.py frontend` 只将专用共享账号信息注入 `VITE_RECRUITER_DEMO_COURSE_ID/EMAIL/PASSWORD`。这些是有意对本机访客公开的 demo 配置；生产构建不设置这三个变量，Sample Course 自动入口不启用。模型 API key、服务 HMAC secret 和数据库凭据不进入 VITE 配置或 Git。

真实浏览器验收（必须使用真实模型和已准备的课程）：

```bash
uv run --with playwright python eval/recruiter-demo-phase-d/browser.py
# 如本机没有 Chromium：uv run --with playwright playwright install chromium
npm --prefix frontend run test:unit
npm --prefix frontend run build
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent_test \
  uv run --directory agent-service --frozen pytest -q
(cd backend && ./mvnw -q -Dtest=StudyControllerTest,StudyAuthorityTest,DenseEvidenceClientTest,DenseRetrievalRoutingTest,CourseQaEvidenceRetrieverTest test)
```

每次浏览器验收创建新 trial 目录，保留全部响应、截图和错误，不覆盖旧结果。确定性测试验证执行与隔离机制；真实浏览器样例只证明当前公开课程上的五个场景可演示，不提升 AU 的泛化结论，也不重新评价 Phase A 检索指标。

Phase D 验收完成后停止求职版开发，不开启后续 Phase。
