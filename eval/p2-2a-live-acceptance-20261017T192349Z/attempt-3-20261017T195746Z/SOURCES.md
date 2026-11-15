# 尝试 3 来源及保留方式

本机交接目录标识 P2-2a-live-20261017T193649Z；通过 Desktop Commander 的 read_file 只读获取本轮更新文档与指定证据，没有启动远程终端或操作浏览器。窗口来源为根目录 WINDOWS_FROZEN_v1.md，不是 originals 中空模板。

窗口 v1 与确认原话的服务器文本副本，与上次提交 e90264c 的 received 文件逐字节相同。新版 MANUAL_LOG 共 43 行，保留旧 18 行并追加；pass_by_user 全为空。正式 reviewer 不填李毅斐，窗口确认人仍按原事实保留。

[received/MANUAL_LOG.csv](received/MANUAL_LOG.csv) 是本次日志文本副本。原 AUTOMATION_LOG/HANDOFF 保留所有追加段；其中账号、个人路径和原页面全文只存本地忽略目录，不提交。源日志引用的截图/其他附件路径仍指向本机目录，没有为断链改写原日志。

本地来源目录：`/home/dev/projects/lecturelens/.data/p2-2a-live-handoff-20261017T195746Z/`。工具返回文本已去掉外层读取/设备标记，保存为 UTF-8/LF；下列哈希对应服务器留存文本，不声称是 Windows 原始字节哈希。FILE_MANIFEST 是用户本机报告的原始字节哈希，和文本归一化哈希口径分开。

| 留存文件 | SHA256（服务器文本） |
| --- | --- |
| AUTOMATION_LOG.md | eb82c5188a5fbce803e46b69366cd4697fbe387a16a94eb2fd98be8089cf9c33 |
| FILE_MANIFEST.csv | e7c4914b8e1b027a22504ad8f81d1dcfc2fe98aac240509527629e4186ae07a1 |
| HANDOFF.md | ce335ca46d4ec32364d1da1c3bd94d7fc60977a07749752a039064edd1e663f9 |
| MANUAL_LOG.csv | f9f9d791bfdc37f33a658d044aab10607f2b560017a3fc67502480aca8636060 |
| WINDOWS_FROZEN_v1.md | a58f7334d59c9256df027c344e3c6886596ba3b1bfad06fa6048f586a3d0925e |
| WINDOW_CONFIRMATION.md | 28adeea70028ffa2d8afe3fe88b54c297fec947327d893908c2bc052492ced70 |
| db/journal-selected.txt | 5157d6b8ad5206b3c5b069467d6a96a27b613245c0de2f6ff6437db6eff4f284 |
| db/mysql-evidence.jsonl | 0302aeb9477baadaac18d5d0d92e6f3f06e84e74891c846b5f9c8449025a4329 |
| db/mysql-schema.txt | 951ce9e72437ced9cadf2077e43e625417bcd5f02a81865f7dadd7f9a49edb7e |
| db/mysql-task.txt | 7edb11129505f0159ed5877ab4af1844c802145db1902797b61f045d526b81c5 |
| db/mysql-usage.txt | b38f2b14eeff3f8cf755c4a4535bc7496d5fc819c1012b39a22867bdc0365e4a |
| db/postgres-evidence.jsonl | 2491af364c8eb4f76c6dda0f31ef14e2f34c19aa0cc2f444c61ec987b346affd |
| db/postgres-schema.txt | 5356f1e435b53cd8d5171432ff3708364f65780796dab01b4d71909316159c31 |
| db/postgres-task.txt | f09917607b8c287b090ce66a3acc51632f3e40b34506ada0d06cf27326072751 |
| db/task-stage.txt | 22dcf193c191ed8d4605b26d4c7b54aa3cf3c7e4c23d527fce1b2141817cd2b0 |
| evidence/18-processing-stage.txt | 12802bf4a405bdee416151bcf9dba77131064f58322128bbe97c48a479cfb6ee |
| evidence/21-g1-start.txt | 531945528dbd70973807eec5daae21ba9b6a8c7f3649a076a0cdd42b84726a44 |
| evidence/23-g1-blocked-full.txt | 91fe2abc308fa29d50654caf92f1f5c7729d0cd7f21d1d16010d49d98447fd8c |

另外已通过工具查看 `evidence/07-upload-preview.png` 和 `evidence/24-g1-blocked.png`：前者可见课程视频播放和字幕，后者可见正确 G1 文本及“学习助手暂不可用”提示。图片包含个人登录账号，不复制进 Git；本机 manifest 报告的原始 SHA256 分别为 `0527dab8f615d1a1ffbf2ec2bf2599556803ee1e8935f71dc073d4508a27e45c`、`a633580b51653ee5c291a2c359f975b562149c01b8fa017f3efddb9481e26a1f`，此次没有额外读取原始二进制来重算。

数据库源文件 db/* 是只读结果投影，具体范围见 DB_READONLY.md；EVIDENCE.csv 只提交引用元数据和内容哈希，课程完整字幕文本留在本地忽略目录。未知成本、无 Run、缺失的反馈/模型调用表分别记录，不以空白或缺表推断零费用。

旧 SUMMARY、RESULTS、received、DESIGN、FREEZE 和历史失败记录均未改写。此次只新增 attempt-3 目录；这是后续尝试，不重新给首次阻塞判成功。没有新跑测试、模型、课程处理或服务；验证仅为文档/CSV、一致性、密钥与文件大小扫描。
