# 一键演示与录屏的实测记录（2026-11-18）

记录 [`scripts/demo/up.sh`](../../scripts/demo/up.sh) 在全新 clone 上的启动时间、内存和冒烟步骤，以及 README 演示录屏的模式与费用。

## 环境

- Linux x86_64，8 核，16 GB 内存，没有 swap；Docker Compose 2.40，Java 21，Node.js 24，uv 0.12，FFmpeg 6.1。
- 本机已有 Maven、npm、uv 的下载缓存，以及 MySQL、Redis、RocketMQ、pgvector 镜像和从源码构建好的 MinIO 镜像。Playwright 的 Chromium 也已安装。新机器第一次运行还要下载这些内容，用时会长很多。
- 本机同时运行着另一套开发栈（Compose 项目 `lecturelens-dev`）。演示脚本没有读取、停止或修改它的容器和数据卷。

## Mock 模式（默认）

在一个新目录 `git clone` 后执行 `scripts/demo/up.sh`。共测了两次：第一次在提交 `69e000d`，从本地工作树 clone；最后一次在提交 `19152e3`，从 GitHub clone，与前一次相比只多了代码格式化和文档。

| 项目 | `69e000d` | `19152e3` |
| --- | --- | --- |
| 到“可以提问”的总时间 | 96.1 s | 95.2 s |
| 启动后的内存增量 | 3.1 GB（9,218 → 12,330 MB） | 2.9 GB（9,650 → 12,599 MB） |
| 冒烟期间峰值（含 Playwright Chromium） | 未单独记录 | 3.7 GB（→ 13,395 MB） |
| `down.sh` 用时 | 23.0 s | 23.3 s |

总时间包括构建 Java JAR、`npm ci` 与前端构建、`uv sync`、下载嵌入模型、启动基础设施、启动三个应用进程、导入演示课程并等待索引 READY。内存是系统已用内存，每 2 秒采样一次。`69e000d` 那次的进程与容器占用：Java 579 MB，Agent 751 MB，前端预览 123 MB；RocketMQ broker 826 MiB，MySQL 466 MiB，MinIO 227 MiB，NameServer 168 MiB，PostgreSQL 31 MiB，Redis 5 MiB。

两次 `down.sh` 之后都没有残留的演示容器或进程，`lecturelens-dev` 的 6 个容器一直在运行。

冒烟步骤：用 [`record-demo.mjs`](../../scripts/demo/record-demo.mjs) 在 Chromium 里走完整流程（Mock 实例）：

1. 登录，打开课程，切换原文、时间轴和学习资料。
2. 课程问答提问，回答带引用；点击引用后，视频和原文跳到对应片段。
3. 提一个课程外的问题。Mock 演示 LLM 仍然引用检索到的第一条证据，没有拒答。这是 Mock 的已知限制，真正的拒答要看真实模式。
4. Study Agent 生成“演示练习（固定测试模型）”，界面标注“Mock 流程测试”。
5. 保存作答，请求证据反馈，得到 Mock 的固定反馈“演示模型不判断作答内容”。

实测过程中失败过两次，都已修复：

- 演示课程的转写较长，超过学习资料生成的 8K 上下文默认值，走了 Mock 没有实现的分段笔记流程。现在由脚本把上下文上限设为 65,536。
- 把 Evidence 片段缩短到 16 秒后，Mock 的固定学习资料没能通过质量校验。Mock 模式改回默认的 60 秒片段；真实模式仍用 16 秒。

## 真实模型模式与录屏

执行 `scripts/demo/up.sh --real --instance real`，`deepseek-flash`，key 来自私有目录，只通过子进程环境传入。录屏前检查过：日志和状态目录里都找不到这个 key。

| 项目 | 结果 |
| --- | --- |
| 到“可以提问”的时间 | 62.5 s（依赖已构建；包含真实模型的翻译、学习资料和章节生成） |
| 录屏 | [lecturelens-walkthrough-real.gif](../../docs/media/lecturelens-walkthrough-real.gif)（4.4 MB，840 px，4 fps）；[MP4](../../docs/media/lecturelens-walkthrough-real.mp4)（1.4 MB，1440×900）；时长 66 s |
| 画面内容 | 课程问答回答带 00:48–01:04 的引用，点击后视频跳到 0:48。课程外问题（红黑树）返回“当前课程内容中没有找到明确依据”。Study Agent 生成解释和两道练习；作答保存后生成第 1 版作答的证据反馈 |

费用按 DeepSeek 官方价计算，录制时段为谷时：

| 范围 | 调用 | Token | 金额 |
| --- | --- | --- | --- |
| 最终录屏所用实例（导入课程 + 一遍录屏） | Java 5 次（翻译 1、学习资料 1、章节 1、课程问答 2），Agent 9 次（练习 Run 5、反馈 Run 4） | 输入 29,193，输出 3,653 | USD 0.0066（全部按未命中缓存计） |
| 此前调试用的实例（已清理，没有逐条记录） | 一次课程导入，两遍完整录屏，一次在 Study 步骤前中止的录屏 | 未记录 | 估计不超过 USD 0.02 |
| 合计 | | | **不超过 USD 0.03** |

调试实例在核算费用之前就用 `--purge` 删除了，所以那部分只能按最终实例的用量估算上界。

## 版权

演示课程是自写的合成内容：字幕见 [binary-search.en.vtt](../../fixtures/demo/binary-search.en.vtt)，视频由 [build-demo-course.sh](../../scripts/demo/build-demo-course.sh) 生成。画面里没有 MIT OCW 或其他第三方课程内容。
