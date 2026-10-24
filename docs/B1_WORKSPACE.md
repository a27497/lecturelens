# B1 默认课程工作区

登录后的默认落点与品牌入口为“我的课程”；显式登录 redirect、上传页 `/upload`、课程 `/tasks/:taskId` 和 `layout=classic` 保持兼容。材料已就绪课程的主操作为“进入学习”。列表依旧使用现有分页读取，不表示精确的最近活动或跨设备续学。

## 交互与状态

- 桌面默认连续工作区保留一份视频与阅读器，右侧复用课程问答、Study Agent、范围、作答、反馈和历史组件。没有 B2/B3 或第二套学习状态。
- 已保存练习优先呈现；新学习目标和课程解释折叠。当前题、作答与反馈使用现有实例；新目标输入即使折叠也不销毁。
- 保存作答是明确操作。未保存修改时暂停新反馈入口；已有反馈继续显示其实际作答版本，另存新版后旧反馈不迁移。作答历史和反馈读取不启动执行。
- 查证沿用 Evidence revision 校验；桌面保留当前题摘要，390px 隐藏重复导航、保留一个返回入口并重排来源文字。播放器和阅读器不会因查证或布局切换重新创建。
- 换题、材料/任务切换保留本页输入；切换 Run/Session 或开始新练习前，对将被丢弃的输入提示确认。取消切换不会把下拉框留在另一条记录的身份。
- 模型记录、Trace、字幕/播放信息和处理详情可展开读取。材料处理进度不表示学习掌握程度。

未改变接口、后端所有权、冻结范围、权限/删除权威、不可变 attempt、request_key/expected_version、反馈关联、取消、预算或 checkpoint 协议。Tutor 与显式 START、START_FEEDBACK 仍分开。

服务端保存记录与本页草稿分开：刷新读取最近可授权的学习记录，不承诺恢复未提交输入或精确题号。未新增笔记、活动聚合、长期记忆或自动评分。

## 视觉与导航

连续模式在桌面保持材料与学习两块统一工作面；手机将材料、练习与Tutor合成一组导航。当前冻结范围与下次选择以紧凑摘要并置；保存、反馈、错误和取消不隐藏到工程详情中。课程库只对处理中的材料显示“材料准备”百分比，就绪课程不显示100%学习完成暗示。

“当前引用”仅标记通过现有Evidence校验的定位，并独立于随后的视频播放位置；普通时间轴跳转不冒充引用。移动查证保留题目上下文与单一返回入口。经典布局和原有URL仍可使用；切换布局不重建作答或播放器。

## 安全的独立预览

从 `frontend/` 运行，先安装前端依赖并构建，再使用**已批准的合成视频**：

```bash
npm ci --ignore-scripts
npm run build
node tests/browser/b1Fixture.mjs --dist dist --media /absolute/path/approved-synthetic.mp4 --port 4391
```

打开 `http://127.0.0.1:4391/__preview`，点击“进入合成课程”。这加载真实 Vue 构建；HTTP 响应来自测试目录下的内存夹具。没有转发到 Java、Agent、数据库或 Provider。预览仅绑定 loopback，Ctrl+C 结束；重启会丢失夹具记录。不要用连接现有 `/api` 代理的 Vite 服务代替这个隔离预览。

该夹具只用于交互和接口接线检查，不证明真实服务持久化、幂等、预算、权限或模型质量。合成媒体不放入 Git；本地预览包可附批准媒体副本。

## 验证

```bash
npm run test:unit
npm run type-check
npm run build
node tests/browser/b1Workspace.mjs --refined --dist dist --media /absolute/path/approved-synthetic.mp4 --chromium /absolute/path/chrome --output /outside/repo/browser-evidence
```

浏览器命令的前置条件：使用非 root 账号、已批准的合成媒体、独立临时浏览器配置，以及有 CPU/内存/进程上限、无外网路由且不能访问生产服务的隔离网络命名空间。不要继承生产环境文件或供应商凭据。脚本只启动本机 HTTP 夹具，启用 Chromium 沙箱；沙箱不可用时关闭夹具并报错，不允许以 `--no-sandbox` 或关闭权限/来源围栏继续测试。上述命令不负责自动创建隔离环境。

当前构建必须显式使用 `--refined`。历史比较只针对已归档的 P2-1 Vue 制品（`5c0dcddb8a0f0b99bd7c0d48d7b2f731c9e0635a`），在同样安全条件下运行：

```bash
node tests/browser/b1Workspace.mjs --legacy-baseline --dist /absolute/path/archived-p2-1-dist --media /absolute/path/approved-synthetic.mp4 --chromium /absolute/path/chrome --output /outside/repo/legacy-browser-evidence
```

两种模式互斥；未选择模式会在启动夹具/浏览器之前失败，避免误用旧手机导航。

浏览器脚本使用独立 Chromium 与测试 HTTP 夹具，阻止页面外部请求。覆盖 1440×900 / 390×844，登录与旧 redirect、真实解码视频、Tutor、显式练习、保存重试、版本/反馈、来源返回与焦点、草稿、历史、范围、取消和异常状态。截图、请求记录和失败试次放到指定的独立目录。

引用专项检查在相同隔离条件下运行：

```bash
node tests/browser/b1EvidenceNavigation.mjs --dist dist --media /absolute/path/approved-synthetic.mp4 --chromium /absolute/path/chrome --output /outside/repo/evidence-navigation
```

专项覆盖学习/材料入口、播放与引用分离、返回与草稿、答案/反馈版本、旧 revision、失权及换课。390px 材料页没有可见题目引用按钮，该组合以真实桌面材料入口点击后、版本校验等待中跨断点完成，记录实际点击宽度；不点击隐藏元素，也不把 HTTP 夹具的拒绝响应算作真实后端权限验收。

本轮不包含真实 Java/Python/PostgreSQL 或付费 Provider 验收。真机软键盘、Safari、屏幕阅读器、大字号、长课程与完整辅助技术顺序仍需独立检查。
