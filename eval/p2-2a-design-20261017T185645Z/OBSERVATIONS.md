# P2-2a 只读调研记录

采集时间：2026-10-17 18:50–18:57 UTC；北京时间 2026-10-18。整理者：Codex，模型辅助源码/来源核查；不是人工教学标注或本次模型质量验收。

基线 `0ea420503b1e6dfa54e568e9d3ba84cc83da9dbd`。只读查询、文件 hash、ffprobe 与一次 ffmpeg 解码；未调用学习模型，未启动/停止/重启 Java 或服务。未读取真实 `.env*` 或 `/proc/*/environ`。MySQL 使用容器既有非 root 应用身份，凭据仅在进程内部传给客户端，未输出或保存。没有写入业务库、DDL 或 GRANT。以下是精选可公开元数据，不保存账号、凭据、全文字幕或私有作答。

## 查询范围与口径

MySQL 容器 `lecturelens-demo-l2-mysql-1`。先查 information_schema 的指定表列名，再分别对以下已存在 schema 做 `START TRANSACTION READ ONLY; SELECT …; COMMIT;`：

- `courselingo`：未删除任务 21 个，成功 2 个，均为 MIT-OCW-linear-7m-8m30s-deepseek-acceptance.mp4。
- `lecturelens_learning_loop`：成功实例按 filename 分组为 strings.mp4 57 个、row-picture.mp4 1 个、knapsack-dev.mp4 1 个、lecture.mp4 1 个、qa-bailian-real-course.mp4 1 个。后两个各 4 条 Evidence，未用于公开课程推荐；不输出其课程正文。
- `lecturelens_l22_completion`、`lecturelens_approval_browser_20261014`、`baseline_asr_20261015`：本次查询未删除且 SUCCEEDED 条件下无行。不表示这些库没有历史失败或已删除记录。
- 未查询 P2-1c 失败 schema 或排查其初始化问题，未访问其他业务容器的课程数据。

代表查询（`<schema>` 仅替换为上述已列库名）：

```sql
START TRANSACTION READ ONLY;
SELECT t.id, u.filename, t.content_revision,
       COALESCE(i.status, 'MISSING') AS index_status, i.indexed_revision,
       COUNT(e.evidence_id) AS evidence_count,
       MIN(e.start_ms) AS min_start_ms, MAX(e.end_ms) AS max_end_ms
FROM <schema>.analysis_task t
JOIN <schema>.upload_session u ON u.id = t.upload_id
LEFT JOIN <schema>.course_evidence e
  ON e.task_id = t.id AND e.revision = t.content_revision
LEFT JOIN <schema>.evidence_index_sync i ON i.task_id = t.id
WHERE t.deleted_at IS NULL AND t.status = 'SUCCEEDED'
GROUP BY t.id, u.filename, t.content_revision, i.status, i.indexed_revision
ORDER BY u.filename, t.id;
COMMIT;
```

候选课另按 task_id/revision/source_type 聚合，校验 `start_ms < 0 OR end_ms < start_ms`，以及 payload 的 retrievable。推荐字符串、row picture、knapsack 均为源/译文两类、全部可检索，无负数/倒置。只对推荐课和 row picture 的源字幕做文本核查；下方仅保留推荐课主题摘要。

PostgreSQL 容器 `lecturelens-agent-postgres-1`，使用 `BEGIN READ ONLY; … COMMIT;`，每个库分别查询：

```sql
SELECT i.course_id, i.revision, i.state,
       COUNT(e.evidence_id) AS indexed_evidence_count,
       MIN(e.start_ms) AS min_start_ms, MAX(e.end_ms) AS max_end_ms
FROM evidence_index i LEFT JOIN indexed_evidence e
  ON e.course_id = i.course_id AND e.owner_id = i.owner_id
WHERE i.course_id IN (
  'task_9530f04391b94c84b1ffc6a49228cecc',
  'task_0119d101510843d18346ba9fa9467740',
  'task_25a77533ec1b4cdba6c9053bfc08c020',
  'task_70ec3dd6189843979174ed6d32d1237f',
  'task_95c8e25dc07944cd82f20d567745738f'
)
GROUP BY i.course_id, i.revision, i.state ORDER BY i.course_id;
```

| PostgreSQL 库 | task_id | revision / state | indexed_evidence_count | start/end ms |
| --- | --- | --- | ---: | --- |
| lecturelens_agent_loop_test | task_9530f04391b94c84b1ffc6a49228cecc | 2 / READY | 16 | 0 / 112590 |
| lecturelens_agent_loop_test | task_0119d101510843d18346ba9fa9467740 | 2 / READY | 36 | 0 / 259679 |
| lecturelens_agent_loop_test | task_25a77533ec1b4cdba6c9053bfc08c020 | 2 / READY | 28 | 0 / 199000 |
| lecturelens_agent | task_70ec3dd6189843979174ed6d32d1237f | 2 / READY | 12 | 0 / 90005 |
| lecturelens_agent | task_95c8e25dc07944cd82f20d567745738f | 2 / READY | 12 | 0 / 90005 |

不能用 `lecturelens_agent` 中没有字符串课推断课程索引丢失；其实际索引在另一个既有库。也不能因库名包含 test 就运行清理式测试。

## 推荐课程的时间与引用清单

MySQL `lecturelens_learning_loop.course_evidence`；task `task_9530f04391b94c84b1ffc6a49228cecc`，revision 2，source_type SUBTITLE。另有同时间的 8 条派生译文，不把中英文重复证据计为 16 段不同教学内容。

| 标记 | 完整 Evidence ID | 本地 start–end 秒 | 来源主题摘要（模型辅助，待人工核定） |
| --- | --- | --- | --- |
| E1 | 9bd47f007377c234299fe25688019167fc9a67ecb6c15208de62e325ff6b72d6 | 0–17.574 | 字符串对象创建后不可修改 |
| E2 | b62f220fcb76d76b21ce64fe9ef259c4de7d0fab84f8bfa68505f89086563139 | 17.574–36.340 | 变量 s 绑定 hello 对象 |
| E3 | 1a05348dcc3b9bfe4317a5d3b0a3e19c68d639e830086170e9dd816bae74393a | 36.340–45.490 | 对索引 0 赋值的设想 |
| E4 | 1a3e475a4e44168f8bb8041d221a18489a27391ece5ac820b8f8c426fee02273 | 45.490–63.954 | 不可变导致索引赋值报错 |
| E5 | 824f92b47f7b1bfc71f31963187bf14a8aca14bdf39a72519097c603a44c3e64 | 63.954–78.020 | 赋新字符串或用字符拼接 |
| E6 | 917d63b091267c2af353c42acc6e2dc9a532613220d4466abdaa027e8e681a5d | 78.020–91.330 | 切片从位置 1 开始，解除旧绑定 |
| E7 | 1a9239e59b1c4112d195de024631c7602621d1dbfaa7fb1cd0ae9270878cca68 | 91.330–107.210 | 新对象、新绑定与仍存在的旧对象 |
| E8 | 7280e2660a31b579f5e3d587f189f5c0178610d2e3f562fbd36e704a7df36ddd | 107.210–112.590 | 重申不可变性 |

## 媒体验证边界

查找仅列本仓 `.data` 与 `/tmp/courselingo` 下 `source.mp4` 路径，不读环境文件。用数据库 upload_id/owner 在内存匹配 `…/assembled/source.mp4`；这里不公开账号/上传私有路径。ffprobe 只读容器/编码/时长，不生成媒体副本。

| 素材 | 文件大小（字节） | ffprobe 时长秒 / 流 | 来源比对 |
| --- | ---: | --- | --- |
| strings Sample Course | 5438854 | 117.016900；h264/aac/mov_text | 两个既有 assembled 副本均可探测；推荐使用既有 recruiter-demo 媒体根。SHA256 `912abfda246ad20d6f35b1c9ef4237bd0f8a68eac3fe871563584f735770f342`，与 `eval/recruiter-demo-phase-d/README.md` 一致 |
| row-picture | 44288956 | 259.692767；h264/aac/mov_text | SHA256 `de85f300c6bd0fa596cb663eb9a676757e0d2740be6b92cf4f8c78cb6f800812`，与 `eval/learning-loop/new-course-source.json` 一致 |
| knapsack-dev | 20994228 | 199.032167；h264/aac/mov_text | 本次未补做公开来源归属确认，不推荐为正式演示课 |
| 90 秒 MIT linear 的两个实例 | 数据库各 8469218 | 本次查找范围内未找到对应 assembled 文件 | STORED 仅为库内状态；不是当前播放器可用结论 |

对 strings 已有本地文件执行 `timeout 15s ffmpeg -v error -ss 36.34 -i <assembled文件> -t 1 -f null -`，退出 0，无解码错误。此项证明一段本地媒体可解码，不证明浏览器鉴权、Range 请求、实际点击或全部目标语义通过。

源码 `MediaPlaybackServiceImpl.java:128–130` 使用 `ChunkStagingPathResolver` 的本地 assembled 路径，不能用 MinIO 对象存在性替代播放器条件。

## 服务与磁盘只读观察

`docker ps` 与 `ss -ltn` 只读查看，未发送控制命令。既有 live 网关配置中 `/api` upstream 指向本机 8080；该端口及历史演示 8084 本次均未监听。8090/8091 有监听，但没有从端口状态推断其模型、feedback 开关、Java 绑定或可执行性；未读取运行时凭据配置。没有探测或修复 P2-1c 冻结进程。

文件系统总计 154894188544 字节，本轮观察已用约 121148743680 字节（78.21%，df 四舍五入显示 79%），可用约 31.41 GiB，距离 85% 约 9.79 GiB。未触及“>85% 或距离 85% 不足 2 GiB”停止线。

主仓原有未跟踪 `eval/baseline-deepseek-20261015T185735Z/DIAGNOSIS.md` 保留，不纳入本次提交；T0b 原 eval 记录亦未改写。本目录只包含设计和只读调研元数据。
