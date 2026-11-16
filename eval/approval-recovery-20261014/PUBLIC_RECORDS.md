# 恢复公开评估记录

仓库以 `matrix-first/raw-parts/` 和 `matrix-final/raw-parts/` 下的 8 个 JSONL 分片保存两份矩阵原始记录。原始 `matrix-first/raw.jsonl` 为 14,205,852 字节，`matrix-final/raw.jsonl` 为 13,626,801 字节。分片按完整 JSONL 行切分，可逐字节恢复原件。

[分片清单](public-record-parts.json)记录拼接顺序，以及每个分片和完整文件的字节数与 SHA-256。从仓库根目录用系统 Python 3 恢复两份原件，并离线复算已保存的 577 条历史记录：

```bash
python3 eval/approval-recovery-20261014/restore_public_records.py
python3 eval/approval-recovery-20261014/verify.py
```

恢复脚本会校验分片及完整文件的 SHA-256，并拒绝覆盖内容不同的已有文件。生成的两份 `raw.jsonl` 由 Git 忽略。整个流程只需 Python 标准库，可离线执行。[复算口径](VERIFY.md)
