# 只读交接来源

读取时间：2026-10-17 UTC；本机验收目录标识 `P2-2a-live-20261017T193649Z`。用户提供了 Windows 目录位置；经 Desktop Commander 对在线的 LAPTOP-51QLNFL2 使用 read_file 只读取得根目录五份文件及交接中引用的两份错误/页面文本，未执行远程 shell 命令，未改本机文件或浏览器设置。

文件传输方式是工具返回的完整文本（各文件均 0 remaining），去除工具外层读取/设备提示后，以 UTF-8 和 LF 换行留存。下列 SHA256 是**服务器留存文本副本**的哈希，不声称是 Windows 源文件原始字节哈希；没有改动记录正文。未读取截图二进制、视频、账号存储或原件目录的空窗口模板。

| 来源相对路径 | 留存文本 SHA256 | 可审阅位置 |
| --- | --- | --- |
| WINDOWS_FROZEN_v1.md | a58f7334d59c9256df027c344e3c6886596ba3b1bfad06fa6048f586a3d0925e | [冻结版](received/WINDOWS_FROZEN_v1.md) |
| WINDOW_CONFIRMATION.md | 28adeea70028ffa2d8afe3fe88b54c297fec947327d893908c2bc052492ced70 | [确认记录](received/WINDOW_CONFIRMATION.md) |
| MANUAL_LOG.csv | bb493ea52c4f557331c26562b2d44aac325960c7c9f970de5d337905174f797b | [人工日志](received/MANUAL_LOG.csv) |
| AUTOMATION_LOG.md | b82dc44e9d4a8d41088f757e800897c6a92d5f292e15901d82f4fec044a506b8 | 本地忽略目录留存，不提交含个人账号的原文 |
| HANDOFF.md | 02b19b89b526fa7bd70a67e24e23e7656d8cc0b5dc5f449233b34dfb14322f50 | 同上，不提交含个人路径/账号的原文 |
| evidence/03-filechooser-error.txt | b374a91c32729c7821ca0a66385fd539e12c87f4bd94225ce7bbfb4ae1873251 | 本地忽略目录；SUMMARY 摘录必要错误文字 |
| evidence/02-upload-blocked.txt | dba528eb8741689af5f27225f943f0e4cdc6d7f48b63b8c65835920bd721a781 | 本地忽略目录；不提交含登录账号的页面全文 |

本地忽略目录：`/home/dev/projects/lecturelens/.data/p2-2a-live-handoff-20261017T194509Z/`。全部七份文本留存于此，原 Windows 文件保持原样。提交的三份 received 副本与对应留存文本相同；其中 reviewer 姓名是用户明确指定的审阅记录。源日志引用的截图、草案、originals 路径属于原本机目录，未全部复制进 Git，链接/引用原样保留。

原自动日志开头的“等待人工冻结”是较早状态，末尾有追加确认与阻塞记录；原 MANUAL_LOG 的较早 NOT_RUN 原因也保留。回填按时间区分这些状态，不覆写旧记录为成功。原日志的首次滚动错误和 FILE_MANIFEST 写入错误均在 SUMMARY 保留。

本次没有新增测试执行；验证仅针对记录一致性、CSV 列、原始文本副本、密钥/大文件与磁盘检查。数据来源是用户交接和本机日志，数据库独立核验未执行。
