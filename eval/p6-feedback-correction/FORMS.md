# 主持、学生与评分者用表

表单是研究材料，不进入产品UI，不新增自动掌握率。下面字段可直接写入manifest JSON；首次真人数据另存私有目录。example-ratings.json是可导入的完整**脚本**评分例，不是两名真人的评分。

## 主持人trial表（每人每题一条）

- trial_id、participant匿名号、condition（reading/feedback）、item_id、顺序、随机分配记录、桌面尺寸（1440×900或1280×800）、开始/干预开始/反馈返回/再答/结束时刻；等待、阅读、再答用时。
- scope：owner_id / course_id / revision / session_id / run_id（练习）/ artifact_id / question_index；data_kind=PILOT。从本人隔离课程的已授权系统数据取得，不手抄答案文本。
- initial_attempt_id与final_attempt_id：明确标哪两次保存构成初答/再答；更多历史版本也全部导出。
- question：冻结原题逐字；`status=complete/incomplete/protocol_violation`，停止原因（退出/超时/反馈失败/课程变更/泄漏/来源映射失败）及原始记录路径。未完成样本进顶层incomplete_trials，保留条件/人/题/原因；不拿另一题替换。每条件分配总数=完整+未完成，主持人核对。
- feedback_exposures：A=[]；B记录run_id、feedback_id、answer_version_at_exposure、at，来自实际可见反馈；如暴露的是旧版本，保留原始文件、标协议违规，不把导出拒绝当数据删除。
- source_checks：evidence_id（真实系统ID）、at、observer（真实观察方式）；如不能确认点击，记unknown，不补填成已看。产品未持久化来源点击；研究侧记录不能称产品遥测。
- discovery：{text:学生再答前原话, at:时间, origin:participant/facilitator_transcription}。无发现也原样记录“不知道/没有发现”。
- final_evidence：{attempt_id:最终ID, claims:[{fact_id:评分者映射的冻结事实ID, evidence_ids:[实际系统ID], reason:学生原话}]}。学生看到的是“引用哪一处，为什么”，不看金标准fact_id。
- 外部帮助、误开参考答案、是否违背A条件、任何主持人提示：单列污染标记，不静默排除。

## 真人课程来源绑定

Mock沿用固定ID；真人导出允许真实course_id和Evidence ID，仍只连接本轮隔离测试数据库。每条trial附source_binding：

```json
{
  "course_id": "系统真实课程ID",
  "revision": 1,
  "material_hash": "measure.digest(冻结course.json)的值",
  "acquired_via": "authenticated_java_evidence",
  "sources": [
    {
      "canonical_id": "h-e1",
      "authority_evidence": {
        "evidence_id": "系统真实ID",
        "text": "与冻结h-e1逐字相同的课程原文",
        "start_ms": 0,
        "end_ms": 10000,
        "source_type": "SUBTITLE"
      }
    }
  ]
}
```

必须覆盖该课程所有冻结段落，ID唯一、原文相同、scope匹配；示例只显示一段，实际须填全。主持人通过已认证Java Evidence接口取得真实scope和每段来源，附原始响应hash/时间，在导出前后重新确认课程revision/权属；`acquired_via`只是可审查来源声明，不是密码学鉴权证明。脚本校验绑定关系与文本，**不替代Java当下授权/删除检查**。若摄取分段或文字不同，不临时放宽匹配或修改金标准；试用前停止，另准备可精确绑定的新材料/新freeze。系统revision可与材料版本号不同，binding使用真实系统revision。

来源与课程准备、冻结题目就绪是试用前主持检查，尚未在浏览器验证。固定题目/参考答案仅供隔离准备和独立评分，真人不见标准答案。若要实时模型生成题目、反馈，必须先有另行调用授权；不要让随机生成题代替固定试题。

## 学生提示（两条件共用）

初答：“请用自己的话回答。没有依据时说明缺少什么。不要使用课程以外资料。”

干预：“请检查原答案。写出你发现的具体问题和理由；没有发现也请直接写。最后提供一份你现在认为合适的答案，并注明课程哪一处支持它。不同意反馈可以保留原答并说明依据。” A只提供课程，B额外展示本次v1的反馈。不要说“请改正这道错误题”，也不要把“同意反馈”当任务目标。

## 评分导入表

每名评分者一个JSON数组，每行字段与example-ratings.json一致：trial_id、item_id、rater_id、initial/final（所有事实点的四值标签）、detected/supported/feedback_flagged（事实ID集合）、feedback_wrong/accepted_wrong_feedback/false_refusal（B布尔，A为null）、honest_insufficiency（不足证据题布尔，其余null）、rationale（逐条原话/段落依据）。

先独立评事实，再揭盲评反馈过程；不把核对记录自动解析成分数。人工评分原始答卷、匿名随机ID映射、两名原分、分歧、裁决与理由分文件保留。计分使用裁决表；一致性必须用原分。没有填写的标签导致脚本拒绝，不能默认正确。

打分例1：read-correct 初答“最多1次”与d-e2相反，d1-f2=incorrect；自查记录明确“1次有误，应为n次”，detected含d1-f2；v2改成n且学生理由引用d-e2，supported含d1-f2。反馈相关字段null。

打分例2：feedback-misled 初答两点正确；故意坏反馈要求n改1，脚本演员接受后v2上界错误。初答d1-f2=correct、再答=incorrect，feedback_wrong/accepted_wrong_feedback=true；supported不能包含d1-f2，即使点开d-e2且acknowledged。此例验证误导不会被计为订正成功，**不是实际学生被误导的证据**。
