# LectureLens Quick Start

本指南使用无密钥 Demo 配置运行真实的异步任务链路。Mock ASR 和确定性 Mock LLM 均在本机运行，不会访问外部 AI 服务。示例视频只用于验证上传和 Pipeline。

## Demo 端口与实例隔离

Demo 默认绑定 MySQL `13306`、Redis `16379`、MinIO `19000/19001`、RocketMQ `19876/18081/20909/20911/20912`，避免常用端口冲突。可复制 `.env.demo.example` 为未提交的 `.env.demo.local` 后修改这些端口；不要把 Demo 值混入 `.env.real-ai.local`。

所有 Demo 脚本使用 `LECTURELENS_DEMO_INSTANCE`（`^[a-z0-9-]{1,32}$`，默认 `default`）生成独立 Compose project `lecturelens-demo-<instance>`。下列命令仅管理该实例，停止时不会删除 volumes：

```powershell
$env:LECTURELENS_DEMO_INSTANCE = "default"
powershell -ExecutionPolicy Bypass -File scripts/demo/check-prerequisites.ps1
powershell -ExecutionPolicy Bypass -File scripts/demo/start-infrastructure.ps1
# 完成后：
powershell -ExecutionPolicy Bypass -File scripts/demo/stop-infrastructure.ps1
```

```bash
export LECTURELENS_DEMO_INSTANCE=default
./scripts/demo/check-prerequisites.sh
./scripts/demo/start-infrastructure.sh
# 完成后：
./scripts/demo/stop-infrastructure.sh
```

需要彻底删除某个 Demo 的数据时才执行 `docker compose --project-name lecturelens-demo-<instance> down -v`。Demo 使用约 2 秒的合成视频，无需 API Key、不访问作者服务器；真实 AI 模式必须使用你自己的 Key。

预期地址：

- 前端：`http://localhost:5173`
- 后端健康：`http://localhost:8080/actuator/health`

## Windows PowerShell

### 1. Clone

```powershell
git clone https://github.com/a27497/lecturelens.git
Set-Location lecturelens
```

### 2. 创建本地 Demo 配置

```powershell
Copy-Item .env.demo.example .env.demo.local
```

`.env.demo.local` 已被 Git 忽略。Demo 配置中的凭据只用于本机 Docker 服务，不是外部服务密钥。

### 3. 检查依赖

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo\check-prerequisites.ps1
```

脚本只检查 Docker、Docker Compose、Java 21、Maven Wrapper、Node.js 24 LTS、npm、FFmpeg、Demo 实际主机端口以及 Windows 保留端口范围，不会安装软件或结束任何进程。

### 4. 启动 Docker 中间件

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo\start-infrastructure.ps1
```

该命令启动 MySQL、Redis、MinIO 和 RocketMQ，不删除任何 volume。

### 5. 启动后端

在第一个终端运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo\start-backend.ps1
```

脚本只向当前进程加载 `.env.demo.local`，不会修改全局环境变量，也不会停止占用 8080 端口的未知进程。等待健康地址返回 `UP`。

### 6. 启动前端

在第二个终端运行：

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

### 7. 生成示例视频

在第三个终端运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo\generate-sample-video.ps1
```

文件生成到 `.demo/lecturelens-sample.mp4`，时长约 2 秒、分辨率 640×360，不依赖系统字体或网络资源。

### 8. 注册并登录

打开 `http://localhost:5173`，使用仅用于本地演示的合成邮箱和密码创建账号，然后在登录页登录。不要使用私人邮箱或常用密码。

### 9. 上传并创建分析任务

进入“上传课程”，选择 `.demo/lecturelens-sample.mp4`。上传完成并看到原视频预览后，选择源语言 English、目标语言简体中文，创建分析任务。

### 10. 查看结果

任务会经历排队和后台处理，最终进入 `SUCCEEDED`。课程详情应显示本地演示提示、时间轴字幕、中文演示翻译、摘要/重点/术语/问答，并在“下载”中提供 SRT、VTT、Markdown、JSON 四类文件。

### 11. 停止本地服务

在前端和后端终端分别按 `Ctrl+C`，然后只停止本项目的 Compose 服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo\stop-infrastructure.ps1
```

该命令只停止当前 `LECTURELENS_DEMO_INSTANCE` 的 Compose project，不会删除 Docker volume。

## Linux/macOS Bash

### 1. Clone

```bash
git clone https://github.com/a27497/lecturelens.git
cd lecturelens
```

### 2. 创建本地 Demo 配置

```bash
cp .env.demo.example .env.demo.local
```

### 3. 检查依赖

```bash
bash scripts/demo/check-prerequisites.sh
```

### 4. 启动 Docker 中间件

```bash
bash scripts/demo/start-infrastructure.sh
```

### 5. 启动后端

在第一个终端运行：

```bash
bash scripts/demo/start-backend.sh
```

### 6. 启动前端

在第二个终端运行：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

### 7. 生成示例视频

在第三个终端运行：

```bash
bash scripts/demo/generate-sample-video.sh
```

### 8. 注册、登录、上传和创建任务

打开 `http://localhost:5173`，使用合成账号注册并登录。上传 `.demo/lecturelens-sample.mp4`，确认原视频预览后，以 English 为源语言、简体中文为目标语言创建分析任务。

### 9. 查看结果

等待任务进入 `SUCCEEDED`，确认 Demo 字幕、翻译、学习包和 SRT/VTT/Markdown/JSON 下载项均已生成。

### 10. 停止本地服务

在前端和后端终端分别按 `Ctrl+C`，然后运行：

```bash
./scripts/demo/stop-infrastructure.sh
```

该命令只停止当前 `LECTURELENS_DEMO_INSTANCE` 的 Compose project。不要添加 `-v`；本指南不会删除已有 volume。
