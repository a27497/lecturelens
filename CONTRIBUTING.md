# Contributing to LectureLens

## 开发环境

建议使用 Java 21、Node.js 24 LTS、npm、Docker Compose 和 FFmpeg。首次运行请从 `.env.demo.example` 创建本地 `.env.demo.local`，不要修改或提交示例文件中的占位边界。

## 分支与 Pull Request

从最新主分支创建一个范围清晰的功能或修复分支。每个 Pull Request 只处理一个主题，说明动机、行为变化、验证命令和已知边界；不要把重构、依赖升级和功能改动混在同一提交链中。

## 后端测试

```bash
cd backend
./mvnw test
```

Windows 使用 `mvnw.cmd test`。新增行为应有不依赖真实外部服务或真实凭据的自动化测试。

## 前端检查

```bash
cd frontend
npm ci
npm run type-check
npm run build
```

## 提交边界

- 不提交 API Key、Token、密码、Cookie、`.env` 或任何真实凭据。
- 不提交真实用户数据、私有地址、对象存储 key、日志或原始模型内容。
- 不提交大型视频；需要验证上传时，使用 `scripts/demo/generate-sample-video.*` 本地生成样例。
- 不提交 `node_modules`、`dist`、`target`、`.demo`、上传缓存、日志或其他生成目录。
