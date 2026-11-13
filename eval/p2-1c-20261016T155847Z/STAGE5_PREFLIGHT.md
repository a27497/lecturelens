# 阶段 5 启动前检查：系统模型凭据路径缺失

用户已批准指定临时 unit 的受控启动、cache OFF 单节冒烟，以及 ASR 正常无 403 后的正式十次；不是等待相同范围的重复启动许可。当前阻碍是获准引用的系统模型 credential 路径未检出。

只通过 sudo grep 检查用户指定的两个 drop-in，输出限于凭据指令名/绝对路径。没有输出 Environment 行、SetCredential 值或任何凭据内容；没有读取所引用的凭据文件，也没有追踪其他配置文件。

- 90-asr-bailian.conf：检出 `LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred`。
- 99-system-models.conf：没有检出任何 LoadCredential*/SetCredential* 指令。只返回布尔值的检查也没有检出标准 Environment 指令；不能据此声称已确认明文密钥，实际存储方式未检查。

因 99 没有可按许可引用的 credential 项，停止启动准备。不复制、不转换或寻找密钥；不修改 live drop-in。需要用户提供允许引用的系统模型 LoadCredentialEncrypted 指令及路径，或修正受控入口。本轮不要求用户提供任何密钥内容。

`lecturelens-p21c-worker-20261017` 未创建；Java 18091 未启动且检查时无监听；live 服务/容器未变。正式提交 0，冒烟及所有真实验收仍未测。原始安全投影、检查方式/复算命令和磁盘 bytes 在 stage5-startup-preflight.json；阶段开始 df 显示 76%，通过磁盘门禁。源码及冻结候选未变，文档/证据变更无需重跑服务测试。
