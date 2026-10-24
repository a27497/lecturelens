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
node tests/browser/b1Workspace.mjs --dist dist --media /absolute/path/approved-synthetic.mp4 --chromium /absolute/path/chrome --output /outside/repo/browser-evidence
```

浏览器脚本使用独立 Chromium 与测试 HTTP 夹具，阻止页面外部请求。覆盖 1440×900 / 390×844，登录与旧 redirect、真实解码视频、Tutor、显式练习、保存重试、版本/反馈、来源返回与焦点、草稿、历史、范围、取消和异常状态。截图、请求记录和失败试次放到指定的独立目录。

本轮不包含真实 Java/Python/PostgreSQL 或付费 Provider 验收。真机软键盘、Safari、屏幕阅读器、大字号、长课程与完整辅助技术顺序仍需独立检查。
