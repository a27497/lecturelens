# 只读诊断与复核

本轮基准 `47d8daf`；只新增本目录文档与证据，不改应用、配置、冻结候选或历史验收记录。未执行或导入任何旧 runtime_support.py、live Python 启动器或密钥加载脚本。

## systemd 加载链

以下是实际使用的安全投影方式；不使用 systemctl cat、show Environment/ExecStart 全值、进程 environ、环境文件 cat 或凭据文件读取。

```bash
systemctl show lecturelens-live-backend.service \
  --property=Id,MainPID,ActiveState,SubState,FragmentPath,DropInPaths,NeedDaemonReload,ExecMainStartTimestampMonotonic
systemctl show lecturelens-live-backend.service --property=EnvironmentFiles,User,Group,WorkingDirectory
systemctl show lecturelens-p21c-worker-20261017.service \
  --property=LoadState,ActiveState,SubState,MainPID
ss -ltn '( sport = :18091 )'
```

对主 unit 及两个已加载 drop-in，仅输出指令名或有限的绝对路径。空 ExecStart= 表示先重置前一条命令，后续最后一个非空 ExecStart 生效。

```bash
sudo -n grep -H -oE \
  '^[[:space:]]*(LoadCredentialEncrypted|LoadCredential|SetCredentialEncrypted|SetCredential|ImportCredential|Environment|EnvironmentFile|ExecStart|ExecStartPre|ExecStartPost|ExecCondition|PassEnvironment|UnsetEnvironment)[[:space:]]*=' \
  /etc/systemd/system/lecturelens-live-backend.service \
  /etc/systemd/system/lecturelens-live-backend.service.d/90-asr-bailian.conf \
  /etc/systemd/system/lecturelens-live-backend.service.d/99-system-models.conf
sudo -n grep -H -oE \
  '^[[:space:]]*(LoadCredentialEncrypted|LoadCredential)[[:space:]]*=[[:space:]]*[A-Za-z0-9_.-]+:/[A-Za-z0-9_./@+-]+' \
  /etc/systemd/system/lecturelens-live-backend.service.d/90-asr-bailian.conf \
  /etc/systemd/system/lecturelens-live-backend.service.d/99-system-models.conf
sudo -n grep -H -oE \
  '^[[:space:]]*EnvironmentFile[[:space:]]*=[[:space:]]*-?/?[A-Za-z0-9_./@%+-]+' \
  /etc/systemd/system/lecturelens-live-backend.service.d/99-system-models.conf
sudo -n grep -H -oE \
  '^[[:space:]]*ExecStart[[:space:]]*=[[:space:]]*/usr/bin/python3[[:space:]]+(/[A-Za-z0-9_./@+-]+)' \
  /etc/systemd/system/lecturelens-live-backend.service.d/90-asr-bailian.conf \
  /etc/systemd/system/lecturelens-live-backend.service.d/99-system-models.conf
```

EnvironmentFile 的结构只提取赋值项名称，正则在等号处结束，不输出值。启动器只提取固定代码符号，不输出配置正文或代码任意字面量。

```bash
sudo -n grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' \
  /home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env
sudo -n stat --format='mode=%a owner=%U group=%G bytes=%s' \
  /home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env
rg -n -o 'dict\(os\.environ\)|os\.environ\.copy\(\)|os\.environ|os\.getenv|SYSTEM_MODEL_MASTER_KEY|CREDENTIALS_DIRECTORY|bailian-asr|read_text|read_bytes|os\.execve|os\.execvpe|subprocess\.Popen|subprocess\.run' \
  .data/system-model-management/deploy-20261016/run-backend-new.py
```

这些投影足以定位入口，不检查密钥值、有效性、环境文件其他值或 launcher 所读取的运行配置。环境文件自身未做内容哈希；不读取凭据文件、数据库密文或进程环境。systemctl 的 LoadCredential/LoadCredentialEncrypted 属性本机只返回 [unprintable]，因此凭据路径结论采用具体 unit/drop-in 的路径投影，不把该字符串当作空配置。

## 冻结身份与源码消费方式

```bash
git show dcc4dda753afd89fafcc2375eaf3cd942dba4b02:backend/src/main/java/com/example/courselingo/systemmodel/SystemModelSecretCipher.java
git show dcc4dda753afd89fafcc2375eaf3cd942dba4b02:backend/src/main/java/com/example/courselingo/systemmodel/SystemModelRuntimeConfiguration.java
sha256sum .data/p2-1c-20261016T155847Z/candidate/backend.jar
```

源码查看只针对 Git 中不含部署凭据的实现，没有调用构造器或解密方法。JAR SHA 与 candidate-artifact.json 一致，包内 META-INF/build-info.properties 投影确认 build.gitCommit=dcc4dda；当前工作树的后续翻译修复不作为本次真实验收运行对象。

## 保护检查与结果

diagnosis.json 记录磁盘 bytes、冻结 JAR 身份、systemd 非敏感投影、环境项名称、启动器固定符号，以及历史证据哈希和既有未提交文件的 inode/size/mtime。该文件只保存结构，不保存 Environment 值或任何凭据内容。closeout.json 是写完方案后的最终保护核验。

```bash
sha256sum --check --quiet eval/p2-1c-credential-20261016T190058Z/SHA256SUMS
git diff --check
```

没有创建临时 unit，没有发出本轮供应商请求，正式试次提交数为 0；没有生成虚构调用/费用台账。冒烟、正式十次及其指标全部未测。PROPOSED_UNIT_DELTA.conf 仅供审查，没有安装到任何 systemd 路径或运行 systemd-run。没有重复已通过的回归测试。
