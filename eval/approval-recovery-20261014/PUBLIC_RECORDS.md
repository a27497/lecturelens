# 公开记录的文件大小处理

原始 `matrix-first/raw.jsonl` 为 14,205,852 字节，`matrix-final/raw.jsonl` 为 13,626,801 字节，超过本轮公开分支的单文件 5 MiB 限额。公开分支将两份文件按完整 JSONL 行拆成 `raw-parts/part-*.jsonl`，每份不超过 4 MiB；未删除试次、失败记录或字段，未修改数值、冻结身份、历史结论与原验算脚本。

`public-record-parts.json` 记录每份分片和原文件的大小与 SHA256。运行下列命令将分片按顺序还原到原路径，再执行冻结的离线验算：

```bash
python3 eval/approval-recovery-20261014/restore_public_records.py
python3 eval/approval-recovery-20261014/verify.py
```

还原文件被 Git 忽略；脚本拒绝覆盖内容不同的已有文件，并逐份检查分片及完整文件的哈希。源仓库中原始提交及原文件保持不变。PR 分支使用公开整理提交，并在提交说明中列出原始提交来源；这次文件拆分不代表重新验收。
