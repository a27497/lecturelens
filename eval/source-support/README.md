# 独立出处支持统计入口

从 P6「给定生成文本 + 它自己的 Evidence → 独立判定」边界提炼；没有修改或导入 P6 worktree 的代码/冻结资产。
不采用“生成模型说自己对了”作为通过标准。此入口不含模型客户端，只校验绑定并汇总外部人工/AI judgments。

`candidate` 包含 data_kind（MOCK/REAL）、course_id/revision、当前快照 evidence 和 items。
每项包含 item_id、claim（闪卡可用“题面 + 答案”；反馈可用“观察 + 下一步”）、自己的 evidence_ids。
`ratings` 绑定整个 candidate 的 SHA-256；每项恰好一个 supported/unsupported/uncertain 和 reason，
supported 还需提供来自该项已附来源的精确引文。引文相同并不保证语义正确，审阅者仍须判断整项断言、条件和限制是否被支持。
不允许用其他项的引用补足该项支持。来源 revision/course 不匹配不得记为 supported。
分母是全部项，uncertain 不算 supported；引用解析率单独统计。

```bash
python3 eval/source-support/measure.py \
  --candidate eval/source-support/example-candidate.json \
  --ratings eval/source-support/example-ratings.json \
  --output .data/p7/support-example-NEW.json
```

示例是合成 **MOCK，不代表质量**：2 项引用均可解析（1.0），1 supported + 1 故意 unsupported，支持率 0.5，
`quality_status=MOCK_NOT_QUALITY`。输出使用 exclusive-create，已有失败报告不会覆盖；每次改内容后须重新冻结并重新提供独立判定。
实际课程快照通过有权 Java Evidence 接口获取，身份/版本由外层导出流程验证；此纯文件统计器不提供授权或绕过网关读取能力。
真实输出、私有资料和判断记录放被忽略的 `.data/`。本轮真实模型审阅 0 次；计划见 [P7 质量评测方案](../p7-flashcards/QUALITY_PLAN.md)。
