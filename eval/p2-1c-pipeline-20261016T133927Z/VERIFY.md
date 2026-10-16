# P2-1c 阶段证据状态

- 当前仅完成只读定位、修复方案汇报及一次独立ASR诊断。业务代码未修改，候选未冻结，worker未启动。
- 方案a/b及Redis DB15原样保留12个已知key的扩展复用授权已提问，答复待定。
- ASR诊断1次物理请求、0重试，HTTP403 AccessDenied.Unpurchased。未修复ASR；当前访问资格拒绝会阻碍完整链路。
- 10次完整链路：未开始。独立恢复：未开始。SIGKILL：0。没有验收成功率或恢复成功声明。
- df初检可用38693998592字节（约36.0GiB），使用率约75.01%（df向上显示76%）；诊断请求前也检查至少2GiB且不超过85%。前后数值见asr-diagnostic.json。
- 在线及上轮隔离schema均只读确认系统模型v10、LEARNING_PACKAGE无数据库绑定、ENV模型lecturelens-local-qwen；无配置写入。
- 未push、未部署、未对受保护容器执行生命周期操作，未读取Redis值/清空/换库。私有响应、凭据、媒体不入Git。
- SHA256SUMS覆盖本目录公开文件（不含清单自身）。语法编译、清单验证及git diff --check用于本阶段证据检查；尚无修复代码测试结果。
