# 复算与重新测量

以下命令在仓库根目录执行。离线复算不启动服务、不调用模型；重新测量会产生 API 费用，两者不能混称。

## 离线复算

```bash
uv venv .data/baseline-asr-20261015/.venv
uv pip install --python .data/baseline-asr-20261015/.venv/bin/python \
  -r eval/baseline-asr-20261015/requirements.txt
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/verify.py
```

这一条命令同时核对冻结全任务统计和追加的 ASR 可用性统计。`summary.json` 保留空输出惩罚 CER；`coverage-asr.json` 仅在 TRANSCRIBE 日志已完成时提供识别 CER。两者均公开，MQ 失败仍保留在全部十次尝试中。概率课只有一次实际转写，无法给出两次 CER 的波动；不得用空任务结果冒充已经执行的 ASR。

MQ 八次投递尝试及七次重试从 `batch-v2/delivery-log.txt` 复算：

```bash
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/delivery-audit.py \
  | cmp - eval/baseline-asr-20261015/delivery-audit.json
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/coverage_asr.py \
  | cmp - eval/baseline-asr-20261015/coverage-asr.json
```

最后一次任务遭 broker 拒收（响应记录磁盘比例 0.91），本批未清理其他文件或调整保护阈值补齐成功样本。重新付费采集前先核实依赖可用性；不得直接重复提交这条失败去覆盖旧记录。

逐项结果哈希与完整 JSON 复算分别使用：

```bash
sha256sum -c eval/baseline-asr-20261015/SHA256SUMS
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/score.py \
  | cmp - eval/baseline-asr-20261015/summary.json
```

原始视频留在 `.data/`，不进入 Git。验证现有素材或按已冻结 URL/哈希下载、重新生成无字幕轨输入：

```bash
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/prepare.py
# 缺失素材时才需要网络下载（没有模型调用）：
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/prepare.py --download
```

原音视频流不转码；若不同 ffmpeg 版本生成不同容器字节，脚本拒绝改写冻结哈希，需使用记录的版本。逐个视频/字幕 SHA、时长和音视频流 SHA 在 `assets.lock.json`。

## 使用原链路重新采集

需要 Java 21、原在线 JAR（SHA 在 runtime identity 中）、该 JAR 的原 ASR 配置、当前可读的受控进程环境及服务依赖。凭据仅在受控进程环境和 Git 忽略的 `.data/`，禁止粘贴到报告或提交。启动辅助脚本会核对 JAR 和关键配置；任一不符就拒绝以旧基线身份运行。

本次使用在线相同的 MySQL/Redis/RocketMQ 基础实例，但 MySQL **独立 schema** `baseline_asr_20261015`，独立 MQ topic/group，独立 loopback 端口 8089、工作目录。未改在线 service、配置或运行时代码。模型服务和本地 embedding 共用在线实例；不声明独占硬件或生产 SLA。

首次建专用 schema 必须为 `utf8mb4_unicode_ci`，否则旧 JAR 的 V13 外键迁移会因默认排序规则差异失败。本次该初始化失败的日志保留，发生在正式调用前。MySQL 账户授权和 MQ topic 应由本地环境管理员配置；只针对该专用 namespace，不得将 JDBC 指向业务 schema。示例（现有本地 demo 容器命名）：

```bash
docker exec lecturelens-demo-l2-mysql-1 sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE baseline_asr_20261015 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON baseline_asr_20261015.* TO courselingo;"'
docker exec lecturelens-demo-l2-rocketmq-broker-1 sh mqadmin updateTopic \
  -n rocketmq-namesrv:9876 -c DefaultCluster -t baseline-asr-20261015
```

已存在的专用评测库可保留；不要重复执行建库或删除旧评测事实。每个 trial 仍新建 upload/task，不复用旧任务输出。准备全新结果目录，以下占位变量由本机受控环境提供：

```bash
ASR_BATCH="eval/baseline-asr-NEW-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ASR_BATCH"
# 另一个终端运行，仅观察索引；不得再将 ASR 指向 HTTP 转发器：
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/meter-index.py \
  --private .data/baseline-asr-20261015 --records "$ASR_BATCH/index-http-calls.jsonl" \
  --source-pid "$ASR_SOURCE_PID"
```

然后依次启动临时评测进程与串行任务：

```bash
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/start-direct.py \
  --source-pid "$ASR_SOURCE_PID" --jar "$ASR_FROZEN_JAR" \
  --asr-config "$ASR_PRIVATE_CONFIG" --batch "$ASR_BATCH"
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/run-batch.py \
  --batch "$ASR_BATCH" --trials 2
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/collect-stages.py \
  --log .data/baseline-asr-20261015/backend-reproduction.log \
  --trials "$ASR_BATCH/trials.jsonl" > "$ASR_BATCH/pipeline-events.jsonl"
.data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/score.py \
  --batch "$ASR_BATCH" --output "$ASR_BATCH/summary.json"
```

启动脚本只在独立本地进程中安装 `BaselineBootstrap.java` 响应观察器：它调用原 Java transport 一次，再读取返回的 usage，返回原响应、传播原异常；不重试、不缓存、不修改 ASR payload/超时/返回值。原 JAR 解包条目逐字节校验，观察器 class 位于额外 classpath，未修改原 class。

原 HTTP 代理批次在根目录保留并标为无效；`run.py`、`run-v2.py`、未执行的 `run-v3.py` 及其源身份用于说明工具迭代。**新的采集入口是 `run-batch.py` → `run-final.py`，不运行旧驱动补齐结果，也不覆写 `batch-v2/`。** 已提交但未完成观测的任务会拒绝自动重交，需先读取现有任务确认状态。

预算在每个新 trial 前检查：成功调用必须有 usage；失败缺 usage 仅为预算控制各预留 1 元（不当作成本数据），旧失败/预检预留 3 元，保护阈值 15 元，为当前试次和 30 元总限制留余量。守卫触发就停止，不调生产参数继续。不得与测试或其他评测并行运行；保持原本的本地模型、batch concurrency、ASR 180s 分块和两路并发。

完成后仅停止辅助脚本记录的评测 PID 和 index meter；保留专用数据库、公开样本记录供审计，不停止原服务。新调用有网络、缓存和模型随机性，不能保证重采集耗时或文本逐字节一致；**已保存记录的离线复算**应完全一致。
