# L1 真实课程 QA 小规模验收（2026-09-15）

## 结果与边界

使用已下载 MIT OCW Python 第 1 讲的 **13:30–16:30** 片段，完成真实视频上传、RocketMQ 调度、FFmpeg 嵌入字幕提取、本地 LLM 翻译/学习资料、CourseEvidence、Python 向量检索、Java QA、前端回答及视频跳转。得到 12 条源字幕与 12 条译文证据。

课程原文来自官方字幕，非 mock，也不是现场 ASR。MOCK_ASR_ENABLED 和 DEMO_MOCK_LLM_ENABLED 均为 false；ASR 回退地址配置为本机不可用端口，防止字幕失败时误用固定 Demo 文本。OCR/VLM 本轮关闭。没有配置或调用付费模型 API。

这证明一条真实课程链路可运行，**不等于完整 L1 或质量评测通过**。五个问题由 AI 检查原始证据，尚无人工金标准；修改后在同样问题上复验，不能把结果作为保留测试集成绩。完整 50 题评测仍按用户决定暂缓。

## 五类问题与发现

| 场景 | 复验观察 |
| --- | --- |
| 算法/食谱的三个要素 | 修复前漏掉停止条件；修复后返回步骤、控制流程、停止方法，3 条引用 |
| 中文问英文课程 | 回答停止条件的作用；仍有 8 条引用，存在重复/不必要引用 |
| 术语改写 | 回答固定用途与可编程计算机的区别，4 条引用；小模型含概括性表达 |
| 01:10 附近的时间问题 | 回答该时段的步骤与控制流程，2 条引用；时间满足后端范围过滤 |
| 课程外 Kubernetes 节点数 | 固定证据不足回复；修复前附带 8 条无关引用，修复后为 0 |

每个返回引用的 ID、revision、源文本前缀和起止时间均与实际 CourseEvidence 比对。复验单次请求耗时约 10–24 秒，包含本地 CPU 推理；这不是吞吐/P95 测量。完整问题、前后答案、引用数量、时间范围、运行时版本见 [机器可读记录](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/pilot-v1/acceptance-2026-09-15.json)。

## 本轮修复

1. 前端 QA 默认 HTTP 等待预算由 55 秒改为 180 秒，覆盖默认冷检索 120 秒 + 生成 45 秒及余量；可通过 `VITE_COURSE_QA_TIMEOUT_MS` 配置。更改后端期限时需要同步调整，客户端超时不再宣称服务器已经停止处理。
2. 新问题开始时清除旧回答，失败后不把旧引用留在新问题下；增加明确的 `RETRIEVAL_UNAVAILABLE` 提示。
3. 标准证据不足回复强制清空引用，即使模型错误地引用了全部候选；浮点数引用索引不再截断成整数。
4. 通用提示要求多部分问题覆盖所有有据部分，并明确缺失部分。漏答案例的“停止条件”实际已在 Top8 中，本轮没有为单题添加词表或扩大检索窗口。

## 浏览器及生命周期

Playwright 使用真实页面和真实后端响应，无 HTTP mock：

- 页面显示本地模型生成的回答；点击首条引用后，视频跳至 **75.36 秒**（原片 14:45.36）。
- 真实停止本轮 Python 检索进程后，QA 返回 503 / RETRIEVAL_UNAVAILABLE；页面显示可读提示，并且旧回答区域清空。
- 另一个新注册用户查询原课程 evidence / QA 均为 404，changes 为空。
- 删除本轮临时课程后，拥有者访问 evidence / QA 也返回 404；重复删除返回 deletedCount=0。三个 outbox 项为 SENT，Java course_evidence 已清空。

本轮没有再次进行运行中重建故障注入；版本变更/并发删除的 Java 回归测试沿用上一工作包。Python 旧向量的即时物理删除尚未实现，仍依赖逻辑过期和后续清理，不能把 Java 入口拒绝读取描述为跨库删除已完成。

## 验证记录

- 后端全量：**1,345 tests，0 failures / errors / skipped**。
- 前端：**38 tests / 13 files 全部通过**，构建通过。
- Python：**24 tests 全部通过**，使用真实 pgvector；Ruff lint/format 通过。
- 本地课程 HTTP、浏览器与生命周期验收通过相应结构/行为断言；语义质量保留上述已知问题。

## CI 镜像来源修复

首次远程 E2E 在启动基础设施时无法拉取 Docker Hub 的 `minio/mc`，尚未进入应用测试。Compose 的 MinIO server/client 改用官方 Quay 同版本镜像并锁定多架构 SHA-256；客户端摘要与原本本地缓存一致。已验证 registry manifest、实际拉取与存储桶初始化。官方客户端发布脚本见 [MinIO docker-buildx.sh](https://github.com/minio/mc/blob/master/docker-buildx.sh)。

## 复现素材与命令

原视频及字幕来源、署名和 CC BY-NC-SA 4.0 条款见 [素材清单](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/pilot-v1/sources.json)。片段以原片 810,000 ms 为起点，视频重编码，字幕裁剪/平移后封装为 MP4 mov_text。原始视频保持不变。派生课程材料及相应问答记录遵循素材许可，不改变项目源码许可。

本地运行时为 llama.cpp **b10977**、Qwen 官方 **Qwen2.5-3B-Instruct Q4_K_M**（固定 revision、下载链接与 SHA-256 见机器记录），以及之前锁定的多语言 MiniLM Embedding。仅把这个小模型用作无 Key 验收配置，没有将其设为项目生产推荐模型。

本轮本地文件在 `.data/l1-acceptance/`：`course-captioned.mp4`、`course.en.vtt`、`canonical-evidence.json`、修复前后完整问答、两张浏览器截图、各阶段日志。`session.local.json` 含测试凭据，已设置 0600 且整个目录被 Git 忽略；不能把该文件加入公开报告。验收任务已删除，视频与模型文件仍在本地，可重建新的课程任务。

在按 [L1 启动文档](L1_DENSE_RETRIEVAL.md) 启动基础设施后：

```bash
# 本轮的本地模型（先从机器记录中的官方地址下载并校验）
.data/l1-acceptance/llama/llama-b10977/llama-server \
  -m .data/l1-acceptance/qwen2.5-3b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 --port 8091 --ctx-size 8192 --parallel 1 --threads 4 --alias lecturelens-local-qwen
```

Java 本轮配置在被忽略的 `.env.acceptance.local`。关键覆盖：OpenAI-compatible 地址为 `http://127.0.0.1:8091/v1`，所有文本 stage model 为 `lecturelens-local-qwen`，启用 dense，嵌入字幕分段 15s，关闭 Mock/OCR/VLM。沿用现有 Demo 数据库/存储配置。CPU 验收的 QA 模型期限为 90s，其余生成使用 180s。服务仅绑定本机。

```bash
python3 scripts/eval/accept-course-qa.py --video .data/l1-acceptance/course-captioned.mp4
# 如任务仍存在，可加 --reuse-task <taskId> 复验，避免重新解析。
uv run --no-project --with playwright python scripts/eval/accept-course-qa-browser.py
# 上一步会停止 processes.json 中本轮登记的 Python 服务。
python3 scripts/eval/accept-course-qa-lifecycle.py
# 最后一步会删除本轮生成的临时任务，不用于用户的历史课程。
```

浏览器脚本需要 Chromium，以及由本轮启动器登记的 `.data/l1-acceptance/processes.json`，停止前检查进程命令；无此运行状态时只执行 HTTP 验收。首次环境的模型下载、课程裁剪和服务启动不是这三个验收脚本自动完成的。它们是验收工具，不是产品启动器。

后续优先补增量/删除同步，再进入 L2。引用重复、弱模型漏答等问题作为后续小型评测集的 bad case；没有标注对照前不添加“准确率提升”简历数据。
