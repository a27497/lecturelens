# P2-1c 验证状态

**修复与候选冻结完成；正式10+1 BLOCKED_ASR_ACCESS_DENIED_UNPURCHASED；真实恢复未演示。**

- 方案a及Redis15保留12个已知key复用已由用户明确确认，见authorization.json、runtime-gates.json。未读取Redis值或清空/换库。
- 148项Java测试通过，0失败/错误/跳过；其中14项上下文测试、21项独立MySQL运行时测试，报告摘要/哈希见tests.json，原始报告本地保存。H2事务测试验证模型I/O在事务外、发布原子性；生成守卫单测验证每次调用的授权检查、取消、预算及冻结引用传递。第一次MySQL启动未执行测试，重跑通过，不计入通过数。
- 离线package成功。冻结JAR SHA256 `209d9b08d44f31269a7649953db850606d262293c00e6665b4500f4000e67a5e`。源码文件、candidate.patch及冻结JAR哈希均校验；运行时109个依赖与冻结JAR一致。未部署。
- 真实本地模型补充验证exit=1：14个map、2个reduce成功，第3个reduce在900秒期限附近超时，未到最终资料生成/质量校验，详见SUMMARY.md。成功调用实际prompt最多1400 token，均未超预算；这不代表整课资料生成通过。它复用旧证据、没有完整链路/发布或服务鉴权集成，不计入10+1。
- 新候选完整链路0/10已提交；独立恢复0/1已提交；worker启动0次，SIGKILL0次。没有已完成批次零重跑的真实证明。
- ASR诊断2次物理请求，均403 AccessDenied.Unpurchased，0重试；无ASR配置修复，费用/用量未知。旧第70片仅能推断同类故障，不能复原其供应商确切错误码。
- 运行前df余量约36GiB；全过程磁盘监测≤85%，见execution-closeout.json。原候选私有原始记录全部通过原SHA清单校验。
- validate_evidence.py只验证身份、计数、scope和预算证据，输出不将受阻验收标为通过。公开SHA256SUMS与私有RAW_SHA256SUMS分别验证；凭据、原始媒体、全文和供应商正文不入Git。
- 无push、无部署、无受保护容器生命周期操作；本轮进程已结束，18091空闲。其他未提交DIAGNOSIS.md保留。
