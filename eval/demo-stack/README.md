# 一键演示与录屏的实测记录（2026-11-18）

记录 [`scripts/demo/up.sh`](../../scripts/demo/up.sh) 在全新 clone 上的启动时间、内存和冒烟步骤，以及 README 演示录屏的模式与费用。

## 环境

- Linux x86_64，8 核，15.7 GB 内存；Docker Compose 2.40，Java 21，Node.js 24，uv 0.12，FFmpeg 6.1。最后一组测量时本机有 4 GB swap，之前的测量没有 swap。
- 本机已有 Maven、npm、uv 的下载缓存，以及 MySQL、Redis、RocketMQ、pgvector 镜像和从源码构建好的 MinIO 镜像。Playwright 的 Chromium 也已安装。新机器第一次运行还要下载这些内容，用时会长很多。
- 早期测量时本机同时运行着另一套开发栈（Compose 项目 `lecturelens-dev`），演示脚本没有读取、停止或修改它。最后一组测量时这套开发栈已由机器所有者停掉。

## 内存上限

演示栈给每个容器设了硬上限（`mem_limit` 与 `memswap_limit` 相同，不会挤进 swap），并压低了 JVM 堆。数值只在 [`stack.py`](../../scripts/demo/stack.py) 的 `CONTAINER_MEMORY`、`BROKER_JAVA_OPTS`、`NAMESRV_JAVA_OPTS`、`JAVA_BACKEND_HEAP` 定义一次。可用内存低于 4,096 MB 时 `up.sh` 拒绝启动（`MIN_AVAILABLE_MB`）。

| 组件 | 上限 | 实测峰值（`3d7fbad`） | 实测峰值（`8ca7b76`） |
| --- | --- | --- | --- |
| RocketMQ broker（含 gRPC proxy，堆 256m） | 896 MiB | 624 MiB | 633 MiB |
| MySQL | 640 MiB | 467 MiB | 468 MiB |
| MinIO | 384 MiB | 218 MiB | 220 MiB |
| RocketMQ NameServer（堆 ≤ 256m） | 384 MiB | 157 MiB | 164 MiB |
| PostgreSQL / pgvector | 256 MiB | 38 MiB | 38 MiB |
| Redis | 64 MiB | 5 MiB | 6 MiB |
| Java 后端进程（`-Xmx768m`） | 堆 768 MiB | RSS 689 MiB | RSS 621 MiB |
| Agent 进程（Python，含 ONNX 嵌入模型） | 无 | RSS 763 MiB | RSS 764 MiB |
| 前端预览进程 | 无 | RSS 134 MiB | RSS 132 MiB |
| **整套（同一采样点的容器与进程之和）** | | **2,966 MiB** | **2,908 MiB** |

第一次加上限时 broker 的堆是 384m、上限 768 MiB，启动阶段被内核 OOM 杀掉（匿名内存 617 MB，大部分在堆外）。`up.sh` 自动停掉了这次启动的容器和进程。改为堆 256m、上限 896 MiB 后通过。

## Mock 模式（默认）

### 学习路径回归

首轮在仓库根目录启动 `scripts/demo/up.sh`，在 `frontend/` 安装 Chromium 后运行 `npm run test:learning-path`。如果演示用 `--instance <name>` 启动，运行测试时设置 `LECTURELENS_DEMO_INSTANCE=<name>`。测试读取该实例合成课程的本地登录凭据，串行运行桌面和 390px 手机宽度。设置 `LECTURELENS_SCREENSHOT_DIR` 可保存每一步的合成课程截图。结束后使用相同实例名执行 `scripts/demo/down.sh --purge`。

CI 在主测试和 Mock HTTP E2E 通过后，在独立演示栈中运行此路径与 `scripts/demo/tests`。路径覆盖原文和学习资料、Tutor 和课程问答引用、开放题作答反馈、选择题错题回看、闪卡自评，以及从「我的课程」恢复视图和暂停位置。这里使用确定性 Mock 服务。

### 启动实测

在一个新目录 `git clone` 后执行 `scripts/demo/up.sh`，再用录屏脚本冒烟，最后 `down.sh`。

| 项目 | `69e000d` | `19152e3` | `b3d83e8`（没有内存上限） | `3d7fbad`（有内存上限） | `8ca7b76`（有上限和归属标签） |
| --- | --- | --- | --- | --- | --- |
| clone 来源 | 本地工作树 | GitHub | GitHub | 本地工作树 | 本地工作树 |
| 到“可以提问”的总时间 | 96.1 s | 95.2 s | 96.6 s | 86.2 s | 89.7 s |
| 启动后的系统内存增量 | 3.1 GB（9,218 → 12,330 MB） | 2.9 GB（9,650 → 12,599 MB） | 未单独记录 | 2.5 GB（2,558 → 5,089 MB） | 1.9 GB（3,960 → 5,899 MB） |
| 冒烟期间峰值增量（含 Playwright Chromium） | 未单独记录 | 3.7 GB（→ 13,395 MB） | 3.4 GB（7,188 → 10,611 MB） | 3.1 GB（→ 5,642 MB） | 2.6 GB（→ 6,530 MB） |
| 冒烟 | 通过 | 通过 | 通过 | 通过 | 通过 |
| `down.sh` 用时 | 23.0 s | 23.3 s | 23.0 s | 22.6 s | 20.9 s（`--purge`） |

总时间包括构建 Java JAR、`npm ci` 与前端构建、`uv sync`、下载嵌入模型、启动基础设施、启动三个应用进程、导入演示课程并等待索引 READY。系统内存是 `free -m` 的 used；`3d7fbad` 那次每约 4 秒采样一次，同时用 `docker stats` 和 `ps` 记录每个容器和进程。`69e000d` 那次的进程与容器占用（没有上限）：Java 579 MB，Agent 751 MB，前端预览 123 MB；RocketMQ broker 826 MiB，MySQL 466 MiB，MinIO 227 MiB，NameServer 168 MiB，PostgreSQL 31 MiB，Redis 5 MiB。

每次 `down.sh` 之后都没有残留的演示容器或进程。

## 资源归属检查（`8ca7b76`）

脚本给每个容器和数据卷打上本次 clone 的归属标签（`io.lecturelens.demo.owner`）。在同一台机器上实测了三种情况：

1. 另一个 clone 留下了同名项目的 4 个数据卷（没有标签）。新 clone 的 `up.sh` 在前提检查阶段拒绝启动，列出这 4 个卷，没有创建任何东西。
2. 正常启动后，同名项目的 8 个容器和 5 个数据卷全部带本 clone 的标签。
3. 在基础设施项目里手动加一个没有标签的数据卷，再执行 `down.sh --purge`：Agent 项目被删除；基础设施项目一个也没删（7 个容器都还在），脚本列出那个外来数据卷并以非零状态退出。删掉外来数据卷后再执行，两个项目都删干净。

全过程前后，本机 `lecturelens-dev-*` 的容器 ID 和数据卷列表完全相同。

之后的版本（`7218823`）改为按 Compose 会使用的确切容器名和卷名检查归属，并把同一实例名的锁放到所有 clone 共用的 `~/.cache/lecturelens-demo/`。在新 clone 上复测：手动建一个没有任何标签、名字与预期相同的 `lecturelens-demo-default_mysql_data` 卷，`up.sh` 在前提检查阶段拒绝并退出 1，没有创建任何容器；删掉这个卷后，Mock 启动到可提问 90.2 s，冒烟通过，`down.sh --purge` 用时 23.0 s，演示容器和卷都为 0，本地状态已删除。`lecturelens-dev-*` 的 8 个容器和 5 个卷前后逐字相同。单元测试增加了无标签同名卷、两个 clone 同时预检、purge 后卷仍在时保留状态，以及导入任务排队、运行、状态读不到或模型不同时都不新建上传。无需 Docker 的单元测试在 [scripts/demo/tests/test_stack.py](../../scripts/demo/tests/test_stack.py)，覆盖项目名白名单、外来资源识别、`docker` 出错不当作空结果、删除时跳过外来项目但继续处理另一个、第一个项目超时不影响第二个、生成的 Compose 文件里每个服务和数据卷都带标签、进程身份不随时区变化。

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

执行 `scripts/demo/up.sh --real --instance real`，`deepseek-flash`，key 来自私有目录，只通过子进程环境传入。录屏前检查过：日志和状态目录里都找不到这个 key。录屏所用课程是在同一个真实模式实例上导入的，所以画面里的译文、学习资料和章节也由 `deepseek-flash` 生成。现在的脚本会把准备课程的模型身份记在实例状态里，只在身份相同时复用，录屏脚本在材料来源模型与当前模型不同时直接报错。

真实模式的启动和录屏是在加内存上限之前做的（提交 `69e000d` 之后的录屏实例）；加上限后没有重跑真实模式。

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
