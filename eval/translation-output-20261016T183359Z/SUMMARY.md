# 在线字幕翻译 OUTPUT_INVALID 诊断与本地修复

范围：在 `b82bebf` 之后修复 Java 翻译可靠性缺陷；仅本地提交。没有部署、供应商调用、在线数据库访问、模型配置变更或服务状态操作。

## 归因与证据边界

- 只读日志重新检出 11 条失败、11 个不同任务，发生于 2026-10-15 19:07:26–19:51:26 UTC。10 条来自历史 PID 2659162，1 条来自 PID 3251334；这些不是当前 PID 4866 新发生的 11 次故障。
- 当前在线进程打开 `.data/system-model-management/deploy-20261016/backend.jar`；包内构建提交为 `bc2e6cc`，SHA-256 为 `b45257e13ac03e313730e193cccad386968e228cc73614616aeedce3dfe0110b`。它不是 P2-1c 冻结候选。
- 11 个任务均记录系统模型调用失败 `OUTPUT_INVALID`，随后翻译步骤抛出 `LlmStageException`。失败调用在客户端返回 `LlmResult` 之前中止；不能据此归因于字幕字段、覆盖率或目标语言校验，也不能把此前成功批次算作该失败调用通过校验。
- 唯一有细分诊断的是 `task_1b5dd375008544258544f7b6f3a2001c`，诊断 ID `4befe79c-b79f-46ac-9341-66cf6fc53b10`：HTTP 200、`finish_reason=length`、`provider_reason=CONTENT_EMPTY`、prompt/completion/total tokens 为 903/3073/3976，业务校验字段均为空。证据来自已有脱敏的 `p13d/diagnostics.json`，没有读取供应商原始响应或课程文本。
- 其余 10 次缺少细分诊断，保留为“客户端 OUTPUT_INVALID，具体原因未记录”。不能追认全部都是截断，也未发现足以证明合法 JSON 被误拒的历史证据。

确认的项目缺陷：旧数据库模型客户端先检查 content 是否为空，再读取 finish_reason；因此空 content 的 length 响应被提前归入通用 OUTPUT_INVALID，异常中的 HTTP 状态变成 null。截断信息无法到达翻译层已有的有限拆分恢复逻辑。供应商返回截断的上游原因及当前真实模型行为仍未验证；本次不推断或调整模型推理选项、上下文、输出 token 上限或预算。

## 修复

1. 仅对数据库路由的 `TRANSLATION_FULL_TEXT + JSON_OBJECT` 使用共用的严格解码器：先识别 length，再检查 content 与 JSON 对象；保留 HTTP 状态、usage 和固定枚举原因。其他 feature 的旧客户端行为及 HTTP 重试边界保持原有路径。
2. legacy 保留原有“缺少 finish_reason 仍可接受合法对象”的兼容行为；V2 继续要求 stop。空输出、非字符串、非法 JSON、非对象 JSON 不会被当作有效译文。
3. typed TRUNCATED 接入已有拆分路径，沿用原有总时限、拆分开关、最小片段、深度与请求尝试上限。不可拆或深度耗尽仍失败；格式错误不增加盲重试。完整字段、覆盖率和语言校验通过后才发布。
4. 失败调用单独记录用量、调用耗时及已消耗的传输重试数；恢复成功时计入汇总，不伪造成功响应或译文。物理调用台账机制保持不变。
5. 阶段安全诊断增加固定枚举 reason/check 和白名单 finishReason，保留既有 OUTPUT_INVALID 对外分类与任务失败行为，不输出模型内容或任意异常文本。

## 验证

最终回归 **311 项通过，0 failure、0 error、0 skipped**；复现命令见 [VERIFY.md](VERIFY.md)。所有模型输出均为测试构造，供应商传输被替换；诊断存储回归使用进程内 H2。

保留了修复前的 RED 记录（2 项，1 failure、1 error）及首次修复后运行（123 项，1 failure）：后者仅是新增测试把 `3976 + 3 × (2 + 1)` 的 total token 期望写错为 3979，实际正确值为 3985。修正测试算术后针对性 126 项通过，无跳过。所有失败日志与报告保留，不改写历史结果。

在线修复效果未测；MySQL 集成测试未运行。本次同步更新一个既有 MySQL 用例的异常类型断言，并用模拟执行服务的 router 用例覆盖相同无降级、无重试边界；这不等同于 MySQL 集成验证。下一步若要确认真实供应商行为，需要另行授权受控验证，采集状态码、finish_reason、content 类型/是否为空、usage 与固定校验原因即可，无需输出原文或响应正文。

原冻结候选、历史验收证据与原有未提交文件的保护结果见 `closeout.json`。P2-1c 凭据门禁仍是独立阻塞。
