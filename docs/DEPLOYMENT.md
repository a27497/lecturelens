# LectureLens 本地部署指南

本文说明如何在本机部署 LectureLens，并使用部署者自己的基础设施密码和 AI Provider 凭据。产品能力与验证数据见[项目主页](../README.md)。

## 部署说明

LectureLens 不提供作者托管的后端、共享账号或共享 API Key。MySQL、Redis、MinIO 和 RocketMQ 运行在使用者自己的环境中；ASR、LLM 与 VLM 请求使用部署者向第三方 Provider 申请的凭据，调用费用和数据合规责任也由部署者承担。

系统优先读取视频内覆盖充分的字幕，只有字幕缺失或覆盖不足时才调用外部 ASR。OCR 与 VLM 均为可选能力，关闭后不影响字幕、翻译、章节、学习资料和导出主链路。

## 环境要求

- Java 21
- Node.js 24 LTS、npm 和 Git
- Docker Desktop 或 Docker Engine，以及 Docker Compose v2
- 可在终端调用的 FFmpeg 与 FFprobe
- Tesseract OCR（可选；不启用 OCR 时无需安装）
- 部署者自己的 SiliconFlow ASR 与 OpenAI-compatible LLM/VLM 凭据

## 1. 克隆仓库

PowerShell、Linux 和 macOS 均可使用：

```bash
git clone https://github.com/a27497/lecturelens.git
cd lecturelens
```

## 2. 创建本地配置

配置模板是 [`.env.real-ai.example`](../.env.real-ai.example)。

Windows PowerShell：

```powershell
Copy-Item .env.real-ai.example .env
```

Linux/macOS：

```bash
cp .env.real-ai.example .env
```

`.env` 已被 Git 忽略。填写后的文件不得提交到仓库，也不要粘贴到 Issue、日志、聊天记录或截图中。后续命令均在仓库根目录执行，除非章节另有说明。

## 3. 基础设施配置

至少检查并替换以下变量：

```text
MYSQL_ROOT_PASSWORD
MYSQL_USERNAME
MYSQL_PASSWORD
REDIS_PASSWORD
MINIO_ROOT_USER
MINIO_ROOT_PASSWORD
STORAGE_MINIO_ACCESS_KEY
STORAGE_MINIO_SECRET_KEY
JWT_ACCESS_SECRET
```

所有 `change-me-*` 值都必须更换。`JWT_ACCESS_SECRET` 至少使用 32 个字符的随机字符串。`STORAGE_MINIO_ACCESS_KEY` 与 `STORAGE_MINIO_SECRET_KEY` 必须分别和 Compose 使用的 `MINIO_ROOT_USER` 与 `MINIO_ROOT_PASSWORD` 保持一致。

模板还包含数据库名、bucket、RocketMQ topic/group、Host Port 和后端连接地址。使用默认端口时无需调整；需要改端口时按第 8 节同步修改。

## 4. ASR 配置

```dotenv
SILICONFLOW_ASR_ENABLED=true
SILICONFLOW_API_KEY=your-own-key
SILICONFLOW_ASR_BASE_URL=https://api.siliconflow.cn
SILICONFLOW_ASR_MODEL=FunAudioLLM/SenseVoiceSmall
COURSELINGO_ASR_TRANSCRIPT_STRATEGY=EMBEDDED_SUBTITLE_FIRST
```

默认策略 `EMBEDDED_SUBTITLE_FIRST` 会先检查内嵌字幕。视频已经包含覆盖充分的字幕时，任务可能没有 ASR 调用记录，这不代表配置失败。

如果要使用其他兼容服务，请填写其实际 Base URL 和模型名，并先确认接口与项目调用方式兼容。

## 5. LLM 配置

```dotenv
OPENAI_COMPATIBLE_ENABLED=true
OPENAI_COMPATIBLE_API_KEY=your-own-key
OPENAI_COMPATIBLE_BASE_URL=https://your-provider.example/v1
OPENAI_COMPATIBLE_MODEL=your-model
```

文本 Provider 必须兼容 OpenAI Chat Completions 接口。翻译、学习资料、章节、课程问答和融合可以分别覆盖模型：

```text
COURSELINGO_AI_MODEL_TRANSLATION
COURSELINGO_AI_MODEL_LEARNING_PACKAGE
COURSELINGO_AI_MODEL_CHAPTER
COURSELINGO_AI_MODEL_QA
COURSELINGO_AI_MODEL_FUSION
```

不需要分别路由时，可以让这些变量保持模板中的同一模型。模型名称必须是 Provider 当前实际开放的名称。

## 6. VLM 配置

启用视觉分析：

```dotenv
COURSELINGO_VISION_ANALYSIS_ENABLED=true
OPENAI_COMPATIBLE_VISION_API_KEY=your-own-key
OPENAI_COMPATIBLE_VISION_BASE_URL=https://your-provider.example/v1
OPENAI_COMPATIBLE_VISION_MODEL=your-vision-model
```

视觉 Provider 必须支持 OpenAI-compatible 多模态请求。Vision Base URL 可以和文本 LLM 相同，也可以不同；Vision Model 必须支持图片输入，不能直接假定文本模型也具备视觉能力。

[`.env.real-ai.example`](../.env.real-ai.example) 中的 Qwen3-VL 配置来自保留的真实视频回归。Provider 下架或重命名模型后，应替换为当前可用的视觉模型。

关闭视觉分析：

```dotenv
COURSELINGO_VISION_ANALYSIS_ENABLED=false
```

关闭 VLM 不影响基础字幕、翻译、章节、学习资料和导出。

## 7. OCR 配置

启用本地 OCR：

```dotenv
COURSELINGO_VISION_OCR_ENABLED=true
COURSELINGO_VISION_OCR_COMMAND=tesseract
COURSELINGO_VISION_OCR_LANGUAGE=chi_sim+eng
```

确保 `tesseract` 可在启动后端的同一终端中执行，并已安装所配置的语言包。

不使用 OCR：

```dotenv
COURSELINGO_VISION_OCR_ENABLED=false
```

关键帧、OCR 和 VLM 使用独立开关；没有 OCR 结果时，应分别检查命令、语言包和 OCR 开关。

## 8. Host Port 与后端连接映射

| Docker Host Port | 后端连接配置 |
| --- | --- |
| `MYSQL_HOST_PORT` | `MYSQL_JDBC_URL` 中的 MySQL 端口 |
| `REDIS_HOST_PORT` | `REDIS_PORT` |
| `MINIO_API_HOST_PORT` | `STORAGE_MINIO_ENDPOINT` |
| `ROCKETMQ_NAMESRV_HOST_PORT` | `ROCKETMQ_NAME_SERVER` |
| `ROCKETMQ_PROXY_HOST_PORT` | `ROCKETMQ_ENDPOINT` |

修改容器 Host Port 时，必须同步修改右侧后端连接配置。只改 Host Port 会让容器正常启动，但后端仍连接旧端口。

MinIO Console 端口不用于后端连接。普通使用者通常也不需要修改 RocketMQ Broker 的 `10909`、`10911`、`10912` 端口。

## 9. 启动基础设施

```powershell
docker compose --env-file .env up -d
docker compose --env-file .env ps
```

Compose 配置见 [`compose.yaml`](../compose.yaml)。它会启动 MySQL、Redis、MinIO、RocketMQ NameServer 和 RocketMQ Broker/Proxy，并初始化 MinIO bucket。确认容器状态正常后再启动后端。

## 10. Windows PowerShell 启动后端

在仓库根目录使用进程级环境变量加载器：

```powershell
foreach ($line in [IO.File]::ReadLines((Resolve-Path ".env"))) {
    $trimmed = $line.Trim()

    if (-not $trimmed -or $trimmed.StartsWith("#")) {
        continue
    }

    $parts = $trimmed -split "=", 2

    if ($parts.Count -ne 2) {
        throw "Invalid .env entry: $trimmed"
    }

    $name = $parts[0].Trim()
    $value = $parts[1].Trim()

    if ($name -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
        throw "Invalid environment variable name: $name"
    }

    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

Set-Location backend
.\mvnw.cmd spring-boot:run
```

变量只加载到当前 PowerShell 进程，不会修改用户级或系统级环境变量。保持该终端运行。

后端健康检查：

```text
http://localhost:8080/actuator/health
```

预期状态为 `UP`。

## 11. Linux/macOS 启动后端

不要直接执行 `source .env`。`MYSQL_JDBC_URL` 等值可能包含 `&`，简单 source 会把它解释为 shell 运算符。

在仓库根目录逐行加载：

```bash
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"

  if [ -z "$line" ] || [[ "$line" == \#* ]]; then
    continue
  fi

  key="${line%%=*}"
  value="${line#*=}"

  if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Invalid environment variable name: $key" >&2
    exit 1
  fi

  export "$key=$value"
done < .env

cd backend
./mvnw spring-boot:run
```

保持终端运行，并访问 `http://localhost:8080/actuator/health` 确认状态为 `UP`。

## 12. 启动前端

另开终端，在仓库根目录执行：

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

浏览器访问 `http://localhost:5173`。开发服务器默认把 API 与健康检查请求代理到本地 `8080` 端口。

## 13. 首次使用

1. 打开前端并注册本地账号。
2. 登录后进入“上传课程”。
3. 选择本地课程视频。
4. 等待分片上传和媒体校验完成。
5. 选择源语言与目标语言。
6. 创建分析任务。
7. 在任务详情页查看实时进度。
8. 完成后查看原文、翻译、章节、学习资料、问答和视觉证据。
9. 下载 SRT、VTT、Markdown 或 JSON。

视频有合格内嵌字幕时，系统可能直接使用字幕；否则调用 ASR。OCR 和 VLM 是否产生结果取决于本地配置。处理时间与第三方费用取决于视频长度、所选模型和网络环境。

## 14. 停止服务

在前端和后端终端按 `Ctrl+C`，然后在仓库根目录停止中间件：

```powershell
docker compose --env-file .env down
```

`down` 会停止并移除 Compose 容器与网络，但保留持久数据。不要使用 `down -v`，除非明确希望连同 MySQL、Redis、MinIO 和 RocketMQ 的持久卷一起删除；删除前应先备份需要保留的数据。

## 常见问题

| 问题 | 检查方式 |
| --- | --- |
| 后端无法连接 MySQL/Redis | 运行 `docker compose --env-file .env ps`，检查密码和端口 |
| MinIO 上传失败 | 检查 MinIO 用户、密码、endpoint 和 bucket 配置 |
| AI 返回 401 | 检查 API Key、Base URL 和模型名 |
| 没有 ASR 调用记录 | 视频可能已经使用内嵌字幕 |
| 没有视觉分析结果 | 检查 VLM 开关、Vision API Key、Vision Base URL 和视觉模型名 |
| 没有 OCR 结果 | 检查 Tesseract、语言包和 OCR 开关 |
| 前端无法调用后端 | 检查后端健康地址和 `8080` 端口 |
| 端口冲突 | 修改 Host Port，并同步更新第 8 节列出的后端连接地址 |

## 安全说明

- 只使用部署者自己的基础设施密码和 AI Key，不要共享账号或凭据。
- `.env`、课程视频、日志、任务工作目录和生成制品不得提交到 Git。
- 第三方 AI 可能接收字幕或视频帧；启用前应确认 Provider 条款、费用、数据区域与合规要求。
- 不要在 Issue、PR、截图或故障日志中粘贴 API Key、Authorization、对象存储 key、本地路径或原始模型响应。
- LectureLens 当前面向本地部署，不承诺商业多租户隔离、在线 SaaS 可用性或性能 SLA。
