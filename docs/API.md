# LectureLens API

## 统一响应格式

所有后端接口统一返回 `ApiResponse<T>` 结构。成功响应 `code` 固定为 `"0"`，`message` 固定为 `"ok"`。`traceId` 优先读取请求头 `X-Trace-Id`，未提供时由后端生成 UUID；当前不接入真实链路追踪组件，E3 会继续增强。

```json
{
  "code": "0",
  "message": "ok",
  "data": {},
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

## 错误响应格式

错误响应同样使用 `ApiResponse<T>` 结构。`code` 使用统一错误码，`message` 使用默认错误信息或业务异常自定义信息，`data` 可用于承载字段级校验错误等安全上下文，不返回堆栈信息。

```json
{
  "code": "COMMON_VALIDATION_FAILED",
  "message": "请求参数校验失败",
  "data": {
    "fieldName": "字段错误说明"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

## 安全响应头

普通 API 与 Actuator 响应会带基础安全响应头：`X-Content-Type-Options=nosniff`、`X-Frame-Options=DENY`、`Referrer-Policy=no-referrer`、`Cache-Control=no-store` 和 `Pragma=no-cache`。这些 header 不改变现有 JWT 登录、refresh token 或 Bearer access token 鉴权语义。

## Auth 接口

| Method | Path | 鉴权 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 否 | 用户注册 |
| POST | `/api/auth/login` | 否 | 用户登录并签发 token |
| POST | `/api/auth/refresh` | 否 | 使用 refresh token 获取新 access token |
| POST | `/api/auth/logout` | 是 | 退出登录并失效 refresh token |
| GET | `/api/me` | 是 | 获取当前用户信息 |

B5 当前已实现 `POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/refresh` 和 `GET /api/me`。登录成功签发 access token 和 refresh token；refresh token 原文只在响应中返回，数据库只保存 refresh token hash。`/api/me` 只接受 access token，不接受 refresh token。退出登录尚未实现。

### POST /api/auth/register

创建用户账号，不签发 access token 或 refresh token。密码只保存 BCrypt 哈希值，不返回原始密码或 `password_hash`。

请求示例：

```json
{
  "email": "demo@example.com",
  "password": "Password123!"
}
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "userId": 1,
    "email": "demo@example.com",
    "status": "ACTIVE"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

注册错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_VALIDATION_FAILED` | 400 | 邮箱格式错误、密码为空、密码长度不符合要求或请求体验证失败 |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | 邮箱已存在 |
| `AUTH_PASSWORD_WEAK` | 400 | 密码不满足服务端强度规则 |

### POST /api/auth/login

校验邮箱、密码和用户状态，登录成功后签发 JWT access token 和随机 refresh token。refresh token 原文只在响应中返回一次，数据库只保存 refresh token hash。

请求示例：

```json
{
  "email": "demo@example.com",
  "password": "Password123!"
}
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "accessToken": "jwt-access-token",
    "refreshToken": "refresh-token",
    "tokenType": "Bearer",
    "expiresIn": 3600,
    "user": {
      "userId": 1,
      "email": "demo@example.com",
      "status": "ACTIVE"
    }
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

登录响应不包含 `password`、`passwordHash`、`tokenHash` 或 JWT secret。

登录错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_VALIDATION_FAILED` | 400 | 邮箱格式错误、密码为空或请求体验证失败 |
| `AUTH_INVALID_CREDENTIALS` | 401 | 用户不存在或密码错误 |
| `AUTH_USER_DISABLED` | 403 | 用户状态不是 `ACTIVE` |

### POST /api/auth/refresh

校验 refresh token 并执行轮换。刷新成功时撤销旧 refresh token，签发新的 access token 和新的 refresh token。数据库只保存 refresh token hash，不保存原文。

请求示例：

```json
{
  "refreshToken": "refresh-token"
}
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "accessToken": "new-jwt-access-token",
    "refreshToken": "new-refresh-token",
    "tokenType": "Bearer",
    "expiresIn": 3600,
    "user": {
      "userId": 1,
      "email": "demo@example.com",
      "status": "ACTIVE"
    }
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

刷新响应不包含 `password`、`passwordHash` 或 `tokenHash`。

刷新错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_VALIDATION_FAILED` | 400 | refreshToken 为空或请求体验证失败 |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | refresh token 不存在或无效 |
| `AUTH_REFRESH_TOKEN_REVOKED` | 401 | refresh token 已撤销 |
| `AUTH_TOKEN_EXPIRED` | 401 | refresh token 已过期 |
| `AUTH_USER_DISABLED` | 403 | 用户状态不是 `ACTIVE` |

### GET /api/me

根据 `Authorization: Bearer <accessToken>` 获取当前登录用户基础信息。接口只接受 access token，refresh token 不能用于 `/api/me`。返回用户信息以数据库中的 `user_account` 记录为准，不使用 token claim 中的 email 或 status 作为最终事实来源。

请求头示例：

```http
Authorization: Bearer access-token
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "userId": 1,
    "email": "demo@example.com",
    "status": "ACTIVE"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

当前用户响应不包含 `password`、`passwordHash`、`refreshToken` 或 `tokenHash`。

当前用户错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `AUTH_INVALID_CREDENTIALS` | 401 | token 对应用户不存在 |
| `AUTH_USER_DISABLED` | 403 | 用户状态不是 `ACTIVE` |

## Upload 接口

所有 Upload 接口必须鉴权，所有上传资源必须按服务端认证得到的 `user_id` 过滤。

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/api/uploads/sessions` | 创建上传会话 |
| POST | `/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}` | 上传单个分片 |
| GET | `/api/uploads/sessions/{uploadId}/missing-chunks` | 查询缺失分片 |
| POST | `/api/uploads/sessions/{uploadId}/complete` | 完成上传并合并 |
| GET | `/api/uploads/{uploadId}` | 查询上传会话 |
| DELETE | `/api/uploads/{uploadId}` | 取消上传 |

上传接口要求：

- 不信任客户端传来的 `owner_id`。
- 不从请求体、URL、Header 或 Query 参数接收 `userId` 作为 owner 判断依据。
- B12 已统一上传会话 owner scope：基于 `uploadId` 的 chunk 上传、缺失分片查询和 complete 合并均按 Bearer access token 得到的当前 `user_id` 查询会话。
- 非本人上传会话与不存在会话使用不暴露 owner 信息的业务错误语义，不在响应中返回 owner `userId`。
- `CREATED -> UPLOADING` 和 `CREATED/UPLOADING -> STORED` 状态更新按 `uploadId + user_id` scope 执行；`UPLOADED` 仅保留为旧数据兼容状态。
- 不信任客户端传来的 `Content-Type` 和原始文件名。
- 服务端生成 MinIO 对象路径。
- B9 当前以本地临时分片 `.part` 文件是否存在作为缺失分片查询依据；Redis chunk 状态后续按 TODO 接入。

### POST /api/uploads/sessions

创建上传会话。当前 B7 只创建会话记录，不接收文件内容，不执行 chunk 上传、缺失分片查询、complete 合并或 MinIO 业务存储。`userId` 来自 Bearer access token 解析和数据库用户查询，不来自请求体。服务端会生成 `uploadId` 和内部 `objectKey`，但 `objectKey` 不返回给前端。

请求头示例：

```http
Authorization: Bearer access-token
```

请求示例：

```json
{
  "filename": "lesson-01.mp4",
  "sizeBytes": 524288000,
  "chunkSizeBytes": 5242880,
  "totalChunks": 100,
  "fileMd5": "d41d8cd98f00b204e9800998ecf8427e"
}
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "uploadId": "up_xxx",
    "status": "CREATED"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

创建上传会话响应不包含 `objectKey` 或 `userId`。允许扩展名为 `mp4`、`mov`、`mkv`、`webm`；扩展名统一按小写保存。`fileMd5` 必须是 32 位十六进制字符串，服务端统一按小写保存。文件名只用于展示，不能包含 `/`、`\`、Windows 盘符样式或控制字符，不能作为对象存储 key。

创建上传会话错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `COMMON_VALIDATION_FAILED` | 400 | 请求体验证失败 |
| `UPLOAD_INVALID_EXTENSION` | 400 | 文件扩展名不在允许列表或缺少扩展名 |
| `UPLOAD_INVALID_FILENAME` | 400 | 文件名为空、包含路径分隔符或 Windows 盘符样式 |
| `UPLOAD_INVALID_MD5` | 400 | fileMd5 不是 32 位十六进制字符串 |
| `UPLOAD_INVALID_CHUNK` | 400 | sizeBytes、chunkSizeBytes 或 totalChunks 不是正数 |

### POST /api/uploads/sessions/{uploadId}/chunks/{chunkIndex}

上传单个 chunk。该接口只接收一个分片并保存到后端本地临时分片目录，为缺失分片查询和 complete 合并提供输入；不合并文件、不直接上传 MinIO、不返回 `objectKey` 或本地临时路径。MinIO 持久化在 complete 校验全部通过后统一执行。

`chunkIndex` 统一使用 0-based：第一个分片为 `0`，最后一个分片为 `totalChunks - 1`。`userId` 来自 Bearer access token 解析和数据库用户查询，不来自请求体或请求参数。服务端会根据 `uploadId` 查询 `upload_session`，并校验该会话属于当前用户。

请求头示例：

```http
Authorization: Bearer access-token
Content-Type: multipart/form-data
```

multipart 字段：

| Field | 说明 |
| --- | --- |
| `file` | 当前 chunk 文件 |

请求示例：

```http
POST /api/uploads/sessions/up_xxx/chunks/0
Authorization: Bearer access-token
Content-Type: multipart/form-data
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "uploadId": "up_xxx",
    "chunkIndex": 0,
    "uploaded": true,
    "status": "UPLOADING"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

成功响应不包含 `objectKey`、`localPath`、`userId`、原始文件名或任何 token/hash 字段。

允许上传 chunk 的会话状态为 `CREATED` 和 `UPLOADING`。`CREATED` 状态首次成功上传 chunk 后更新为 `UPLOADING`；`UPLOADING` 状态继续保持 `UPLOADING`。`MERGING`、`COMPLETED`、`FAILED`、`CANCELLED` 状态不允许上传 chunk。

chunk 大小校验：

- `file` 必须存在且大小大于 0。
- `file.size <= upload_session.chunk_size_bytes`。
- 非最后一个 chunk 的大小必须等于 `upload_session.chunk_size_bytes`。
- 最后一个 chunk 的大小必须等于 `size_bytes - chunk_size_bytes * (total_chunks - 1)`。

上传单个分片错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `COMMON_FORBIDDEN` | 403 | 无权访问资源 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `UPLOAD_SESSION_NOT_FOUND` | 404 | 上传会话不存在或 uploadId 格式不合法 |
| `UPLOAD_SESSION_FORBIDDEN` | 403 | 当前用户无权访问该上传会话 |
| `UPLOAD_INVALID_CHUNK` | 400 | chunkIndex 越界或 chunk 大小不符合会话要求 |
| `UPLOAD_EMPTY_CHUNK` | 400 | file 字段缺失或 chunk 为空 |
| `UPLOAD_SESSION_STATUS_INVALID` | 409 | 上传会话状态不允许上传 chunk |
| `UPLOAD_CHUNK_SAVE_FAILED` | 500 | 本地临时分片保存失败 |

### GET /api/uploads/sessions/{uploadId}/missing-chunks

查询上传会话的缺失分片。当前 B9 只读取后端本地 staging 目录中的 `.part` 文件，计算已上传和缺失的 chunk index。本接口不上传 chunk，不合并文件，不修改 `upload_session.status`，不返回 `objectKey`，也不返回本地临时路径。Redis chunk 状态后续再接入，本轮以 staging 目录 `.part` 文件为依据。

`chunkIndex` 统一使用 0-based：第一个分片为 `0`，最后一个分片为 `totalChunks - 1`。`userId` 来自 Bearer access token 解析和数据库用户查询，不来自请求参数。服务端会根据 `uploadId` 查询 `upload_session`，并校验该会话属于当前用户。

请求头示例：

```http
Authorization: Bearer access-token
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "uploadId": "up_xxx",
    "totalChunks": 5,
    "uploadedChunks": [0, 2, 4],
    "missingChunks": [1, 3],
    "allUploaded": false,
    "status": "UPLOADING"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

成功响应不包含 `objectKey`、`localPath`、`userId`、原始文件名或任何 token/hash 字段。

查询规则：

- 如果 session 目录不存在，`uploadedChunks` 为空，`missingChunks` 返回 `0` 到 `totalChunks - 1`。
- 只统计文件名格式为 `{数字}.part` 的文件。
- 只统计范围内的 chunk index：`0 <= chunkIndex < totalChunks`。
- 忽略 `.tmp`、`abc.part`、`999.part`、`-1.part` 等无效文件。
- `uploadedChunks` 和 `missingChunks` 均按升序返回。
- `CREATED`、`UPLOADING`、`MERGING`、`COMPLETED`、`FAILED`、`CANCELLED` 状态都可以查询。

查询缺失分片错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `COMMON_FORBIDDEN` | 403 | 无权访问资源 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `UPLOAD_SESSION_NOT_FOUND` | 404 | 上传会话不存在 |
| `UPLOAD_SESSION_FORBIDDEN` | 403 | 当前用户无权访问该上传会话 |
| `UPLOAD_INVALID_SESSION_ID` | 400 | uploadId 为空、格式非法或包含路径穿越字符 |

### POST /api/uploads/sessions/{uploadId}/complete

完成上传会话并合并本地 staging 分片。服务端完成分片完整性、顺序合并、最终大小、MD5 和视频头校验后，使用会话中服务端生成的 `object_key` 将 assembled 文件写入 MinIO；只有写入成功后才把 `upload_session.status` 更新为 `STORED`。本接口不创建分析任务、不发送 RocketMQ 消息，也不调用 FFmpeg、ASR、LLM 或 LangChain4j。

`userId` 来自 Bearer access token 解析和数据库用户查询，不来自请求体或请求参数。服务端会根据 `uploadId` 查询 `upload_session`，并校验该会话属于当前用户。请求体当前不需要传递 `objectKey`、`userId` 或本地路径。

请求头示例：

```http
Authorization: Bearer access-token
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "uploadId": "up_xxx",
    "status": "STORED",
    "sizeBytes": 10485760,
    "fileMd5": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

成功响应不包含 `objectKey`、`localPath`、`userId`、原始文件名或任何 token/hash 字段。

合并规则：

- 只允许 `CREATED` 和 `UPLOADING` 状态执行 complete。
- `STORED`、legacy `UPLOADED`、`MERGING`、`COMPLETED`、`FAILED`、`CANCELLED` 等状态不允许重复或继续 complete。
- 必须检查 `0 <= chunkIndex < totalChunks` 范围内的所有 `{chunkIndex}.part` 文件是否存在。
- 任意 chunk 缺失时返回业务错误，并在错误信息中包含缺失的 chunk index 列表。
- 按 `0.part`、`1.part`、`2.part` 顺序合并到 `{chunkStagingDir}/{userId}/{uploadId}/assembled/source.{ext}`。
- assembled 本地路径不返回给前端。
- 合并后必须校验文件大小等于 `upload_session.size_bytes`。
- 合并后必须校验 MD5 等于 `upload_session.file_md5`。
- size 或 MD5 校验失败时不更新 `upload_session.status`。
- B11 增强基础视频头校验：`mp4` / `mov` 必须在文件前部包含合法 `ftyp` box，`mkv` / `webm` 必须以 EBML magic bytes `1A 45 DF A3` 开头。
- 视频头校验只做轻量格式识别，不调用 FFmpeg，不解析完整编码，不执行杀毒或转码。
- 视频头校验失败时不更新 `upload_session.status`，不删除源 `.part` 分片。
- 校验通过后先按扩展名映射视频 Content-Type 并写入 MinIO，再更新 `upload_session.status` 为 `STORED`；不修改 `object_key`，不删除源 `.part` 分片。
- MinIO 写入失败时不更新为 `STORED`、不清理 Redis chunk state、不删除 `.part` 或 assembled 文件，也不返回完成成功。

完成上传错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `COMMON_FORBIDDEN` | 403 | 无权访问资源 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `UPLOAD_INVALID_SESSION_ID` | 400 | uploadId 为空、格式非法或包含路径穿越字符 |
| `UPLOAD_SESSION_NOT_FOUND` | 404 | 上传会话不存在 |
| `UPLOAD_SESSION_FORBIDDEN` | 403 | 当前用户无权访问该上传会话 |
| `UPLOAD_SESSION_STATUS_INVALID` | 409 | 上传会话状态不允许 complete |
| `UPLOAD_CHUNK_MISSING` | 400 | 任意必需分片缺失 |
| `UPLOAD_ASSEMBLED_SIZE_MISMATCH` | 409 | 合并后的文件大小与上传会话记录不一致 |
| `UPLOAD_ASSEMBLED_MD5_MISMATCH` | 409 | 合并后的文件 MD5 与上传会话记录不一致 |
| `UPLOAD_INVALID_VIDEO_HEADER` | 400 | 合并后的文件基础视频头校验失败 |
| `UPLOAD_MERGE_FAILED` | 500 | 本地分片合并或读取失败 |

### B14 前端上传页接入说明

B14 前端新增独立上传页，页面按以下顺序调用既有 Upload API：选择文件后在浏览器端计算文件 MD5，创建上传会话，查询缺失分片，仅上传 `missingChunks` 中的分片，最后调用 complete 合并。所有 Upload 请求沿用前端 localStorage 中的 access token 并发送 `Authorization: Bearer <accessToken>`，不要求用户手动输入 token。

前端上传页只接入上传链路，不创建分析任务，不调用任务、AI、结果、Redis、RocketMQ、FFmpeg、ASR 或 LLM 相关接口。页面不展示 access token、`objectKey`、后端本地路径或 `userId`，请求体也不传 `userId` / `ownerId`。

## Task 接口

所有 Task 接口必须鉴权，所有任务必须按 `user_id` 过滤。

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/api/tasks` | 创建分析任务并发送 RocketMQ 消息 |
| GET | `/api/tasks` | 查询当前用户任务列表 |
| GET | `/api/tasks/{taskId}` | 查询任务详情 |
| POST | `/api/tasks/{taskId}/retry` | 重试失败任务 |
| POST | `/api/tasks/{taskId}/cancel` | 取消任务 |
| POST | `/api/tasks/batch-delete` | 批量逻辑删除终态课程 |
| GET | `/api/tasks/{taskId}/events` | SSE 任务进度推送 |

创建任务接口只负责：

- 校验上传记录归属当前 `user_id`。
- 新完成上传返回 `STORED`；前端不应继续以 `UPLOADED` 作为新上传完成条件。
- 调用 C10 `AnalysisRateLimitService` 做任务创建限流。
- 创建 `analysis_task`。
- 通过 C2 `AnalysisTaskStateService` 将任务从 `CREATED` 合法推进到 `QUEUED`，并间接写入 `task_log`、刷新 C8 进度快照。
- 发送 RocketMQ 消息到 `courselingo-analysis-task`。
- 不直接执行 FFmpeg / ASR / LLM / LangChain4j。

C11 已实现 `GET /api/tasks/{taskId}/events` SSE 任务事件流。C13 已实现 `POST /api/tasks/{taskId}/retry` 和 `POST /api/tasks/{taskId}/cancel` 任务控制接口。C14 已实现 `POST /api/tasks` 创建分析任务接口。C15 已实现 `GET /api/tasks` 任务列表和 `GET /api/tasks/{taskId}` 任务详情查询接口。当前没有可调用的结果或制品接口；上述其他 Task API 仍按后续 TODO 分步实现。

用户可见任务列表、详情和所有 owner-scoped 下游入口都显式要求 `analysis_task.deleted_at IS NULL`。逻辑删除任务统一表现为 `TASK_NOT_FOUND`，不会暴露其他用户或已删除任务的存在性。

### GET /api/tasks

查询当前用户自己的任务列表。接口必须使用 `Authorization: Bearer <accessToken>`，只接受 access token，不接受 refresh token。服务端只按 Bearer access token 解析出的当前 `user_id` 做 owner scope 过滤，不从 Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属判断依据。

请求头示例：

```http
Authorization: Bearer access-token
```

Query 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `status` | 否 | 合法 `AnalysisTaskStatus`，例如 `RUNNING`、`FAILED` |
| `page` | 否 | 默认 `1`，必须大于等于 `1` |
| `pageSize` | 否 | 默认 `20`，必须在 `1` 到 `100` 之间 |

查询规则：

- 数据源为 MySQL `analysis_task`，按当前用户 `user_id` 过滤。
- `status` 为空时不过滤状态，非空时必须是合法任务状态。
- 默认固定按 `created_at DESC` 排序。
- 不接受客户端传入任意排序字段，避免 SQL 注入和字段越权。
- 列表查询不发送 RocketMQ 消息，不调用 Runner，不执行 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "items": [
      {
        "taskId": "task_xxx",
        "uploadId": "up_xxx",
        "targetLanguage": "zh-CN",
        "status": "RUNNING",
        "progressPercent": 35,
        "currentStage": "EXTRACT_AUDIO",
        "errorCode": null,
        "errorMessage": null,
        "retryCount": 0,
        "maxRetryCount": 3,
        "createdAt": "2026-06-27T10:00:00",
        "updatedAt": "2026-06-27T10:01:00",
        "startedAt": "2026-06-27T10:01:00",
        "finishedAt": null
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 1
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

列表响应不包含 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key、secret key、password hash 或 refresh token hash。`errorMessage` 会做脱敏和长度控制。

前端任务列表页基于现有列表响应在浏览器端做状态分组筛选，不新增后端字段。分组为：全部、进行中、已完成、失败、已取消；进行中包含 `CREATED`、`QUEUED`、`RUNNING`、`RETRYING` 等非终态，已完成对应 `SUCCEEDED`，失败对应 `FAILED`，已取消对应 `CANCELED` / `CANCELLED`。列表页展示中文状态、进度、当前阶段、目标语言、创建时间、最近更新时间和脱敏失败原因；失败或取消任务的“重新分析”入口继续调用 `POST /api/tasks/{taskId}/retry`，retry 会创建新任务且不覆盖原失败任务。

### GET /api/tasks/{taskId}

查询当前用户自己的任务详情。接口必须使用 `Authorization: Bearer <accessToken>`，只接受 access token，不接受 refresh token。服务端只按 Bearer access token 解析出的当前 `user_id` 和路径中的 `taskId` 做 owner scope 查询，不从 Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属判断依据。任务不存在或不属于当前用户时统一返回 `TASK_NOT_FOUND`。

请求头示例：

```http
Authorization: Bearer access-token
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "taskId": "task_xxx",
    "uploadId": "up_xxx",
    "targetLanguage": "zh-CN",
    "status": "RUNNING",
    "progressPercent": 35,
    "currentStage": "EXTRACT_AUDIO",
    "retryCount": 0,
    "maxRetryCount": 3,
    "createdAt": "2026-06-27T10:00:00",
    "updatedAt": "2026-06-27T10:01:00",
    "startedAt": "2026-06-27T10:01:00"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

详情响应不包含 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key、secret key、password hash 或 refresh token hash。`errorMessage` 会做脱敏和长度控制。详情查询不发送 RocketMQ 消息，不调用 Runner，不执行 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。

### POST /api/tasks

创建当前用户自己的分析任务。接口必须使用 `Authorization: Bearer <accessToken>`，只接受 access token，不接受 refresh token。服务端只按 Bearer access token 解析出的当前 `user_id` 和请求体中的 `uploadId` 做 owner scope 校验，不从请求体、Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属判断依据。

请求头示例：

```http
Authorization: Bearer access-token
Content-Type: application/json
```

请求示例：

```json
{
  "uploadId": "up_xxx",
  "targetLanguage": "zh-CN"
}
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "taskId": "task_xxx",
    "uploadId": "up_xxx",
    "status": "QUEUED",
    "targetLanguage": "zh-CN"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

创建规则：

- `uploadId` 必须非空、长度不超过 64，且只能使用服务端允许的 ID 字符，不允许路径穿越、斜杠、反斜杠或本地路径格式。
- `targetLanguage` 必须非空且长度不超过 32。
- 上传会话必须存在且属于当前 Bearer access token 对应用户；不存在和非 owner 都返回不暴露 owner 信息的业务错误。
- `STORED` 正式上传和 legacy `UPLOADED` 历史上传允许创建分析任务；其他状态返回 `UPLOAD_SESSION_STATUS_INVALID`。
- 创建前调用 C10 `AnalysisRateLimitService.checkAndConsume(currentUserId)`；限流拒绝时返回 `TASK_RATE_LIMITED`，响应不暴露 Redis key 或 `userId`。
- 成功创建时先插入 `analysis_task`，初始状态为 `CREATED`，再通过 C2 `AnalysisTaskStateService` 推进到 `QUEUED`，不绕过状态机直接乱改状态。
- 状态推进会间接写入 `task_log` 并刷新 C8 进度快照。
- 成功推进到 `QUEUED` 后通过 C3 Producer 发送 Topic `courselingo-analysis-task`、Tag `ANALYSIS_CREATED`、Message Key `taskId` 的 RocketMQ 消息；消息体包含 `taskId`、`uploadId`、`userId`、`targetLanguage`、`requestId` 和 `createdAt`。
- 当前策略不是生产级分布式事务消息：MySQL 任务创建和状态推进先于 MQ 发送。若 MQ 发送失败，接口返回 `MQ_SEND_FAILED` 并补充 `task_log` WARN 记录，不假装成功；后续可通过补偿任务或事务消息增强。
- 创建接口不直接调用 Runner，不在 HTTP 请求线程中执行真实分析任务，不调用 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。

创建任务响应不包含 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key 或 secret key。

创建任务错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `COMMON_VALIDATION_FAILED` | 400 | 请求体验证失败或 `targetLanguage` 不合法 |
| `UPLOAD_INVALID_SESSION_ID` | 400 | `uploadId` 为空、格式非法或包含路径穿越字符 |
| `UPLOAD_SESSION_NOT_FOUND` | 404 | 上传会话不存在或不属于当前用户 |
| `UPLOAD_SESSION_STATUS_INVALID` | 409 | 上传会话状态不是 `STORED` 或 legacy `UPLOADED` |
| `TASK_RATE_LIMITED` | 429 | 任务创建过于频繁 |
| `MQ_SEND_FAILED` | 500 | 创建任务状态推进后发送 RocketMQ 消息失败 |

### POST /api/tasks/{taskId}/retry

重新分析当前用户自己的失败或已取消任务。接口必须使用 `Authorization: Bearer <accessToken>`，只接受 access token，不接受 refresh token。服务端只按 Bearer access token 解析出的当前 `user_id` 和路径中的 `taskId` 做 owner scope 校验，不从请求体、Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属判断依据。

retry 不重置原任务，也不清空原任务错误信息。服务端会读取原任务的 `uploadId` 和 `targetLanguage`，复用创建分析任务链路创建一个新的 `analysis_task`，并按现有创建任务流程投递 `ANALYSIS_CREATED` RocketMQ 消息。这样保留失败任务历史、`task_log` 和 `ai_call_record`，避免重置状态机产生脏状态。

请求头示例：

```http
Authorization: Bearer access-token
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "originalTaskId": "task_failed_xxx",
    "newTaskId": "task_new_xxx",
    "status": "QUEUED",
    "message": "已创建新的分析任务"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

retry 规则：

- 只允许当前状态为 `FAILED` 或 `CANCELED` 的任务重新分析。
- `SUCCEEDED` 返回 `TASK_RETRY_NOT_ALLOWED`，提示“任务已完成，无需重新分析”。
- `CREATED`、`QUEUED`、`RUNNING`、`RETRYING` 返回 `TASK_RETRY_NOT_ALLOWED`，提示“任务正在处理中，不能重复分析”。
- 新任务复用原任务的 `uploadId` 和 `targetLanguage`，并复用 `POST /api/tasks` 的上传归属、上传完成状态、限流、任务创建和 MQ 投递校验。
- 原任务不修改 `status`、`retry_count`、`error_code`、`error_message`、`finished_at`，也不删除任何日志、制品或 AI 调用记录。
- retry 接口不直接调用 Runner，不在 HTTP 请求线程中执行真实分析任务，不调用 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。
- 如果原 upload session 不存在、不属于当前用户或不是 `STORED` / legacy `UPLOADED`，复用创建任务链路返回对应上传错误。

retry 响应不包含 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key 或 secret key。

### POST /api/tasks/{taskId}/cancel

取消当前用户自己的可取消任务。接口必须使用 `Authorization: Bearer <accessToken>`，只接受 access token，不接受 refresh token。服务端只按 Bearer access token 解析出的当前 `user_id` 和路径中的 `taskId` 做 owner scope 校验，不从请求体、Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属判断依据。

请求头示例：

```http
Authorization: Bearer access-token
```

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "taskId": "task_xxx",
    "status": "CANCELED"
  },
  "timestamp": "2026-06-27T00:00:00Z",
  "traceId": "string"
}
```

cancel 规则：

- 允许 `CREATED`、`QUEUED`、`RUNNING`、`RETRYING` 取消。
- `SUCCEEDED`、`FAILED`、`CANCELED` 取消会返回 `TASK_INVALID_STATUS`，本阶段不做幂等成功返回。
- 取消成功后通过 C2 `AnalysisTaskStateService` 推进到 `CANCELED`，间接写入 `task_log` 并刷新 C8 任务进度快照。
- 取消成功后通过 C3 Producer 发送 Topic `courselingo-analysis-task`、Tag `ANALYSIS_CANCEL`、Message Key `taskId` 的 RocketMQ 消息。
- cancel 接口不直接调用 Runner，不在 HTTP 请求线程中执行真实分析任务，不调用 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。
- 当前 HTTP cancel 不直接释放 C9 claim；claim 释放依赖 C5 Runner cancel 路径和既有 claim release 语义。
- 当前策略为“先更新 MySQL 事实状态并写日志，再发送 MQ”。如果 MQ 发送失败，接口返回 `MQ_SEND_FAILED`，并补充 `task_log` WARN 记录；当前不实现生产级分布式事务消息。

cancel 响应不包含 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key 或 secret key。

### GET /api/tasks/{taskId}/events

通过 SSE 推送当前用户自己的任务状态和进度。接口必须使用 `Authorization: Bearer <accessToken>`，只接受 access token，不接受 refresh token。服务端只按 Bearer access token 解析出的当前 `user_id` 做 owner scope 校验，不从 Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属判断依据。

请求头示例：

```http
Authorization: Bearer access-token
Accept: text/event-stream
```

事件类型：

| Event | 说明 |
| --- | --- |
| `snapshot` | 建立连接后立即发送当前任务快照 |
| `progress` | 状态、进度、阶段或错误摘要变化时发送 |
| `heartbeat` | 周期保活事件 |
| `completed` | 任务进入 `SUCCEEDED` 后发送并关闭 SSE |
| `failed` | 任务进入 `FAILED` 后发送并关闭 SSE |
| `canceled` | 任务进入 `CANCELED` 后发送并关闭 SSE |
| `error` | 流内部错误事件，随后关闭 SSE |

`snapshot`、`progress` 和终态事件数据示例：

```json
{
  "taskId": "task_xxx",
  "status": "RUNNING",
  "progressPercent": 35,
  "currentStage": "ASR",
  "errorCode": null,
  "errorMessage": null,
  "updatedAt": "2026-06-27T10:00:00Z"
}
```

当前快照来源优先级：

```text
Redis cl:t:progress:{taskId} -> MySQL analysis_task
```

Redis 只作为短状态读取来源；owner scope 校验始终以 MySQL `analysis_task` 的 `taskId + currentUserId` 查询为准。Redis key 不会返回给前端。

SSE 事件数据不得包含 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key 或 secret key。heartbeat 事件只用于保活，不包含敏感信息。

### C12 前端任务详情页 SSE 接入说明

C12 前端新增任务详情页 `/tasks/:taskId`，用于连接 C11 `GET /api/tasks/{taskId}/events` SSE 任务事件流并展示任务状态、进度、阶段、更新时间、心跳时间和脱敏错误摘要。前端不新增任务创建、任务详情、重试、取消、结果或制品 API 调用。

浏览器原生 `EventSource` 不能设置 `Authorization` 请求头，因此前端使用 `fetch` 读取 `text/event-stream` 响应流，并在请求头中发送：

```http
Authorization: Bearer <accessToken>
Accept: text/event-stream
```

access token 只从浏览器 localStorage 中读取并写入请求头，不拼接到 URL Query，不在页面中展示，也不写入控制台日志。页面只展示 SSE payload 中允许前端展示的字段，不展示 Redis key、`objectKey`、本地路径、`userId`、access token、refresh token、API key 或 secret key。

前端事件处理规则：

- `snapshot`：连接建立后的初始快照，刷新任务状态与进度。
- `progress`：刷新任务状态、进度、阶段和脱敏错误摘要。
- `heartbeat`：只更新页面最近心跳时间，不改变业务状态。
- `completed` / `failed` / `canceled`：刷新终态快照并关闭前端连接状态。
- `error` 或网络断开：展示可读错误，并允许用户手动重新连接。

错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_UNAUTHORIZED` | 401 | 缺少 Authorization header 或不是 Bearer 格式 |
| `AUTH_TOKEN_INVALID` | 401 | access token 非法、签名错误、type 不是 `access`，或使用 refresh token 调用 |
| `AUTH_TOKEN_EXPIRED` | 401 | access token 已过期 |
| `COMMON_VALIDATION_FAILED` | 400 | 任务列表分页或状态参数不合法 |
| `AUTH_INVALID_CREDENTIALS` | 401 | token 对应用户不存在 |
| `AUTH_USER_DISABLED` | 403 | 用户状态不是 `ACTIVE` |
| `TASK_NOT_FOUND` | 404 | 任务不存在或不属于当前用户 |
| `UPLOAD_INVALID_SESSION_ID` | 400 | 创建任务时 uploadId 为空或格式非法 |
| `UPLOAD_SESSION_NOT_FOUND` | 404 | 创建任务时上传会话不存在或不属于当前用户 |
| `UPLOAD_SESSION_STATUS_INVALID` | 409 | 创建任务时上传会话状态不是 `STORED` 或 legacy `UPLOADED` |
| `TASK_INVALID_STATUS` | 409 | 当前任务状态不允许 cancel |
| `TASK_RETRY_NOT_ALLOWED` | 409 | 当前任务状态不允许重新分析 |
| `TASK_RATE_LIMITED` | 429 | 创建任务过于频繁 |
| `MQ_SEND_FAILED` | 500 | 创建 / retry / cancel 状态更新后发送 RocketMQ 消息失败 |

## Result 接口

所有 Result 接口必须鉴权，所有结果必须按任务所属 `user_id` 过滤。

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/api/tasks/{taskId}/results` | 获取任务完整结果概览 |
| GET | `/api/tasks/{taskId}/subtitles` | 获取字幕片段 |
| GET | `/api/tasks/{taskId}/learning-package` | 获取摘要、重点、Q&A、术语表 |
| GET | `/api/tasks/{taskId}/ai-calls` | 获取 AI 调用记录和成本统计字段 |

### GET /api/tasks/{taskId}/results

获取当前登录用户当前任务的结果概览。接口必须使用 `Authorization: Bearer <accessToken>`，服务端只按 access token 解析出的当前用户和 path 中的 `taskId` 做 owner scope 校验，不接受客户端传入的 `userId` / `ownerId`。

响应只聚合已经持久化的 D7-D15 结果数据：源字幕、目标语言字幕、学习包、制品安全元数据、AI 调用记录安全元数据。接口不触发字幕、翻译、学习包或制品生成，不调用 FFmpeg / ASR / LLM / LangChain4j，不发送 MQ，不接入 Runner。

成功响应示例：

```json
{
  "code": "0",
  "message": "ok",
  "data": {
    "taskId": "task_xxx",
    "targetLanguage": "zh-CN",
    "subtitles": [
      {
        "segmentIndex": 0,
        "startMillis": 0,
        "endMillis": 3000,
        "language": "en",
        "sourceText": "hello"
      }
    ],
    "translations": [
      {
        "segmentIndex": 0,
        "startMillis": 0,
        "endMillis": 3000,
        "sourceLanguage": "en",
        "targetLanguage": "zh-CN",
        "translatedText": "你好"
      }
    ],
    "learningPackage": {
      "targetLanguage": "zh-CN",
      "title": "Lesson",
      "summary": "Summary",
      "keyPoints": [],
      "glossary": [],
      "qa": []
    },
    "artifacts": [
      {
        "artifactType": "JSON",
        "language": "zh-CN",
        "fileName": "task_xxx-zh-CN.json",
        "contentType": "application/json; charset=utf-8",
        "sizeBytes": 1234,
        "sha256": "abc123",
        "createdAt": "2026-06-28T10:00:00"
      }
    ],
    "aiCallRecords": [
      {
        "id": 1,
        "callType": "LLM",
        "stage": "TRANSLATION",
        "provider": "mock-llm",
        "model": "mock-model",
        "status": "SUCCEEDED",
        "durationMillis": 100,
        "promptTokens": 10,
        "completionTokens": 20,
        "totalTokens": 30,
        "createdAt": "2026-06-28T10:00:00"
      }
    ]
  },
  "timestamp": "2026-06-28T10:00:00Z",
  "traceId": "string"
}
```

安全边界：
- 响应不包含 `userId`、`objectKey`、本地路径、access token、refresh token、API key、Authorization header 或 secret。
- 制品只展示安全元数据，不提供真实下载链接。
- AI 调用记录只展示安全元数据，不返回 raw prompt、raw response、request fingerprint 或 response fingerprint。
- 字幕、翻译、制品、AI 调用记录不存在时返回空数组；学习包不存在时返回 `null`。
- 任务不存在或不属于当前用户时返回 `TASK_NOT_FOUND`。

## Artifact 下载接口

所有 Artifact 接口必须鉴权，所有制品必须按任务所属 `user_id` 过滤。

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/api/tasks/{taskId}/artifacts/{artifactType}/{language}/download` | 下载当前用户可见任务的指定制品 |

Artifact 类型：

- `SRT`
- `VTT`
- `MARKDOWN`
- `JSON`

### GET /api/tasks/{taskId}/artifacts/{artifactType}/{language}/download

下载当前登录用户已有的生成制品。

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端先以 `taskId + userId` 校验当前用户可见且未逻辑删除的任务，再读取 `taskId + userId + artifactType + language` 范围内的制品。
- 响应体是原始制品文件流；例如 `VTT` 返回 `text/vtt; charset=utf-8`。
- 响应使用 `Content-Disposition: inline`，前端可通过鉴权请求拉取内容后创建 Blob URL 供 `<track>` 使用。
- 响应不得暴露 `objectKey`、本地路径、`userId`、access token、refresh token、API key 或 secret。
- 任务不存在、不属于当前用户或已逻辑删除时统一返回 `TASK_NOT_FOUND`；任务存在且可见但指定制品不存在时返回 `ARTIFACT_NOT_FOUND`。

## Settings 接口

| Method | Path | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/settings/profile` | 是 | 查询用户设置 |
| PUT | `/api/settings/profile` | 是 | 更新用户设置 |
| GET | `/api/settings/providers` | 是 | 查询 ASR / LLM Provider 配置状态，不返回密钥 |

## Ops 接口

Actuator 暴露范围固定为 `health,info,metrics`；`env`、`beans`、`configprops`、`heapdump`、`threaddump`、`loggers`、`prometheus` 等敏感或未接入端点不公开。健康详情策略为 `never`，不会向响应体暴露组件细节、环境变量、主机信息或密钥。

| Method | Path | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/actuator/health` | 否 | 基础健康检查，返回应用自身 UP/DOWN 状态 |
| GET | `/actuator/info` | 否 | 基础信息端点，当前不输出敏感信息 |
| GET | `/actuator/metrics` | 否 | Micrometer metrics 端点，只暴露低基数、无敏感 tag 的业务指标 |
| GET | `/api/debug/build-info` | 否 | 本地 E2E 调试构建信息，只返回应用名、服务端时间、git commit、Java 版本和 active profiles |
| GET | `/api/public/runtime-configuration` | 否 | 公开且无敏感信息的运行模式标记，仅返回 `demoMode`，供前端显示本地 Demo 提示 |

`GET /api/debug/build-info` 的 `gitCommit` 来自最终可执行 JAR 内的 `META-INF/build-info.properties`，属性名为 `build.gitCommit`。构建时未提供该属性或属性为空时返回 `unknown`；正式部署只接受构建时写入的完整 40 位 SHA。该接口不调用 Git、不启动子进程、不读取服务器 checkout 或环境变量作为版本来源。服务器部署同时校验 JAR freshness、JAR 内 SHA、JVM command line 中唯一的 `-jar` 路径和 API 返回值；checkout SHA 本身不能证明运行中的 JAR 已更新。完整部署验证语义见 `docs/DEPLOYMENT.md` 和 `docs/SERVER_RUNTIME.md`。响应使用统一 `ApiResponse` 包装，`data` 字段包含：

```json
{
  "application": "courselingo-pro",
  "time": "2026-06-29T00:00:00Z",
  "gitCommit": "0123456789abcdef0123456789abcdef01234567",
  "javaVersion": "21",
  "activeProfiles": ["local"]
}
```

该端点不读取或返回环境变量明细、数据库连接串、RocketMQ 密码、API key、Authorization header、JWT、用户数据、`objectKey`、本地文件路径、raw prompt 或 raw response。`gitCommit` 无法解析时返回 `unknown`。

Ops 不暴露真实密钥、内部连接串或用户数据。依赖级 readiness 和鉴权后的管理能力尚未实现。

## 前端用户友好错误提示

前端不会把后端原始英文异常、堆栈、token、`objectKey`、本地路径或密钥类字段展示给普通用户。登录、上传、任务、播放和结果页统一把后端 `code`、HTTP 状态、axios timeout / network error 映射为中文提示。

关键映射包括：

| 后端 code / 场景 | 前端提示 |
| --- | --- |
| `AUTH_INVALID_CREDENTIALS` | 邮箱或密码不正确 |
| `COMMON_UNAUTHORIZED` / 401 | 登录已过期，请重新登录 |
| `COMMON_FORBIDDEN` / 403 | 你没有权限操作这个资源 |
| `UPLOAD_SESSION_NOT_FOUND` | 上传任务不存在，请重新选择视频 |
| `UPLOAD_SESSION_NOT_COMPLETED` | 视频还没有上传完成 |
| `TASK_NOT_FOUND` | 分析任务不存在或已被删除 |
| `TASK_INVALID_STATUS` | 当前任务状态不允许这个操作 |
| `TASK_RETRY_NOT_ALLOWED` | 当前任务不能重新分析 |
| `MQ_SEND_FAILED` | 消息队列配置异常，请联系管理员 |
| `AI_PROVIDER_TIMEOUT` | AI 服务响应较慢，请稍后重试 |
| `AI_PROVIDER_FAILED` | AI 服务临时异常，请稍后重试 |
| `MEDIA_PLAYBACK_TOKEN_EXPIRED` | 播放链接已过期，请刷新播放链接 |
| `MEDIA_SOURCE_NOT_FOUND` | 未找到原视频文件 |
| timeout | 服务器响应较慢，请稍后重试 |
| network error | 网络连接失败，请检查服务器是否可访问 |

## 错误码列表

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `COMMON_BAD_REQUEST` | 400 | 请求参数错误 |
| `COMMON_UNAUTHORIZED` | 401 | 未认证或认证已失效 |
| `COMMON_FORBIDDEN` | 403 | 无权访问资源 |
| `COMMON_NOT_FOUND` | 404 | 资源不存在 |
| `COMMON_VALIDATION_FAILED` | 400 | 请求参数校验失败 |
| `COMMON_INTERNAL_ERROR` | 500 | 服务内部错误 |
| `AUTH_INVALID_CREDENTIALS` | 401 | 登录凭据无效 |
| `AUTH_TOKEN_EXPIRED` | 401 | 访问令牌已过期 |
| `AUTH_TOKEN_INVALID` | 401 | 访问令牌无效 |
| `AUTH_USER_DISABLED` | 403 | 用户已被禁用 |
| `AUTH_TOKEN_SIGN_FAILED` | 500 | 访问令牌签发失败 |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | 刷新令牌无效 |
| `AUTH_REFRESH_TOKEN_REVOKED` | 401 | 刷新令牌已撤销 |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | 邮箱已存在 |
| `AUTH_PASSWORD_WEAK` | 400 | 密码强度不符合要求 |
| `UPLOAD_INVALID_EXTENSION` | 400 | 上传文件扩展名不允许 |
| `UPLOAD_INVALID_FILENAME` | 400 | 上传文件名不合法 |
| `UPLOAD_INVALID_MD5` | 400 | 上传文件 MD5 不合法 |
| `UPLOAD_INVALID_CHUNK` | 400 | 上传分片参数不合法 |
| `UPLOAD_INVALID_SIGNATURE` | 400 | 上传文件签名校验失败 |
| `UPLOAD_CHUNK_OUT_OF_RANGE` | 400 | 上传分片序号超出范围 |
| `UPLOAD_SESSION_NOT_FOUND` | 404 | 上传会话不存在 |
| `UPLOAD_SESSION_FORBIDDEN` | 403 | 无权访问上传会话 |
| `UPLOAD_INVALID_SESSION_ID` | 400 | 上传会话 ID 不合法 |
| `UPLOAD_EMPTY_CHUNK` | 400 | 上传分片不能为空 |
| `UPLOAD_CHUNK_SAVE_FAILED` | 500 | 上传分片保存失败 |
| `UPLOAD_CHUNK_MISSING` | 400 | 上传分片缺失 |
| `UPLOAD_SESSION_STATUS_INVALID` | 409 | 上传会话状态不允许当前操作 |
| `UPLOAD_SESSION_CREATE_FAILED` | 500 | 创建上传会话失败 |
| `UPLOAD_ASSEMBLED_SIZE_MISMATCH` | 409 | 合并文件大小校验失败 |
| `UPLOAD_ASSEMBLED_MD5_MISMATCH` | 409 | 合并文件 MD5 校验失败 |
| `UPLOAD_INVALID_VIDEO_HEADER` | 400 | 上传文件视频头校验失败 |
| `UPLOAD_MERGE_FAILED` | 500 | 合并失败 |
| `STORAGE_INVALID_OBJECT_KEY` | 400 | 存储对象 key 不合法 |
| `STORAGE_SOURCE_FILE_INVALID` | 400 | 存储源文件不合法 |
| `STORAGE_OPERATION_FAILED` | 500 | 对象存储操作失败 |
| `STORAGE_CONFIGURATION_INVALID` | 500 | 对象存储配置不合法 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `TASK_NOT_OWNER` | 403 | 无权访问该任务 |
| `TASK_INVALID_STATUS` | 409 | 任务状态不允许当前操作 |
| `TASK_RETRY_NOT_ALLOWED` | 409 | 任务不允许重新分析 |
| `TASK_RATE_LIMITED` | 429 | 任务创建过于频繁 |
| `TASK_DUPLICATE_CLAIMED` | 409 | 任务已被其他执行器领取 |
| `AI_PROVIDER_TIMEOUT` | 504 | AI Provider 调用超时 |
| `AI_PROVIDER_FAILED` | 502 | AI Provider 调用失败 |
| `ARTIFACT_NOT_FOUND` | 404 | 制品不存在 |

## LONG-6 result fields

`GET /api/tasks/{taskId}/results` now includes full-text transcript fields in addition to timeline subtitles:

- `sourceFullText`: source transcript assembled from ASR subtitle segments.
- `sourceParagraphs`: paragraph list derived from `sourceFullText`.
- `translatedFullText`: stable double-newline join of the same ordered segment translations returned in `translations`. A successful task persists both outputs atomically; this field may be empty only while translation is still running or when translation fails before the transaction commits.

TRANSLATION-DUAL-OUTPUT-R1 requires `translations.size() == subtitles.size()` for every successful task. Segment timestamps and indexes inherit the matching source subtitles. The Pipeline writes one aggregate translation `ai_call_record` even when deterministic batching or split retries perform multiple provider calls.

The response must not expose object keys, local storage paths, raw prompts, raw LLM responses, API keys, or provider secrets.

## 原视频播放预览 API

### 申请上传视频播放令牌

`POST /api/uploads/{uploadId}/playback-token`

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端按 access token 解析当前用户，并校验 `uploadId + userId` 归属、可播放上传状态和受控本地缓存存在。
- 响应继续使用统一 `ApiResponse` 包装，`data` 结构如下：

```json
{
  "token": "short-lived-playback-token",
  "expiresAt": "2026-07-04T12:00:00Z",
  "playbackUrl": "/api/media/uploads/1001/stream?token=short-lived-playback-token"
}
```

响应不得返回 `objectKey`、本地文件路径、`userId`、access token、refresh token 或任何密钥。

### 申请任务原视频播放令牌

`POST /api/tasks/{taskId}/playback-token`

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端按 `taskId + userId` 校验任务归属，再解析任务绑定的上传记录并复用同一套上传归属、状态和源文件校验。
- 前端只需要持有 `taskId`，不需要从任务详情页暴露 `uploadId`。
- 响应结构与上传视频播放令牌一致。

### 播放原视频流

`GET /api/media/uploads/{uploadId}/stream?token=<playbackToken>`

- 该接口不要求 `Authorization` header，供浏览器 `<video>` 标签直接使用。
- 服务端必须校验播放令牌签名、过期时间、`uploadId` 绑定关系和 owner scope。
- 支持 HTTP Range 请求：合法 Range 返回 `206 Partial Content`，无 Range 返回 `200 OK`，非法或不可满足 Range 返回 `416 Range Not Satisfiable`。
- 响应头包含 `Accept-Ranges: bytes`、`Content-Length`、`Content-Type`、`Content-Disposition: inline`；Range 响应额外包含 `Content-Range`。
- 服务端按范围流式读取视频文件，不把完整视频读入内存。
- 当前播放源为上传 complete 后生成的本地 assembled 原视频文件；接口不暴露本地路径或对象存储 key。
- 不做转码、多清晰度、自适应码率、硬字幕烧录、分享链接、下载按钮或管理员绕过。浏览器能否播放取决于原始视频编码和容器兼容性。

### 探测上传原视频自带字幕

`GET /api/uploads/{uploadId}/embedded-subtitles`

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端按 `uploadId + userId` 校验 owner scope、上传状态和 assembled 原视频存在性。
- 服务端通过 `ffprobe` 只探测原视频容器内的 subtitle stream，不读取外挂字幕文件，不读取 AI VTT artifact，不写数据库。
- 响应不包含本地路径、`objectKey`、`userId`、token、secret 或字幕全文。

成功响应示例：

```json
{
  "status": "FOUND",
  "selectedStreamIndex": 3,
  "tracks": [
    {
      "streamIndex": 3,
      "codecName": "subrip",
      "language": "zho",
      "title": "Chinese",
      "defaultTrack": true,
      "supported": true,
      "unsupportedReason": ""
    }
  ]
}
```

`status` 取值：

| status | 说明 |
| --- | --- |
| `FOUND` | 检测到至少一条可提取的文本软字幕轨道 |
| `NOT_FOUND` | 未检测到原视频内嵌字幕轨道 |
| `UNSUPPORTED` | 检测到字幕轨道，但均为暂不支持的格式 |

支持提取为 WebVTT 的字幕 codec：`subrip`、`srt`、`ass`、`ssa`、`mov_text`、`webvtt`。PGS、DVD、DVB、xsub 等图片字幕当前不做 OCR 或文字提取。

### 下载上传原视频自带字幕 WebVTT

`GET /api/uploads/{uploadId}/embedded-subtitles/{streamIndex}/download`

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端再次按 `uploadId + userId` 校验 owner scope，并确认 `streamIndex` 对应的是支持的 subtitle stream。
- 服务端通过 `ffmpeg -map 0:<streamIndex> -c:s webvtt` 将原视频内嵌文本软字幕提取为 WebVTT，缓存到后端本地 `storage/embedded-subtitles/{uploadId}/track-{streamIndex}.vtt`。
- 响应体为 `text/vtt;charset=utf-8` 文件流，不使用统一 `ApiResponse` 包装。
- 接口不返回缓存路径、本地视频路径或 `objectKey`。

### 探测任务原视频自带字幕

`GET /api/tasks/{taskId}/embedded-subtitles`

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端按 `taskId + userId` 校验任务归属，再解析任务绑定的上传源并复用上传字幕探测规则。

### 下载任务原视频自带字幕 WebVTT

`GET /api/tasks/{taskId}/embedded-subtitles/{streamIndex}/download`

- 需要 `Authorization: Bearer <accessToken>`。
- 服务端按 `taskId + userId` 校验任务归属，再解析任务绑定的上传源并复用上传字幕下载规则。
- 前端任务详情页“课程原视频”播放器使用该接口下载 WebVTT 文本后创建 Blob URL，并通过自定义 overlay 显示原视频自带字幕；该字幕来源不等同于 AI 生成的 VTT artifact。

新增错误码：

| Code | HTTP Status | 说明 |
| --- | --- | --- |
| `MEDIA_PLAYBACK_TOKEN_INVALID` | 401 | 播放令牌无效 |
| `MEDIA_PLAYBACK_TOKEN_EXPIRED` | 401 | 播放令牌已过期 |
| `MEDIA_PLAYBACK_FORBIDDEN` | 403 | 无权播放该视频 |
| `MEDIA_SOURCE_NOT_FOUND` | 404 | 原视频源文件不存在 |
| `MEDIA_RANGE_NOT_SATISFIABLE` | 416 | 请求的视频 Range 不可满足 |
| `MEDIA_SUBTITLE_PROBE_FAILED` | 500 | 原视频自带字幕探测失败 |
| `MEDIA_SUBTITLE_UNSUPPORTED` | 422 | 原视频自带字幕格式暂不支持 |
| `MEDIA_SUBTITLE_EXTRACTION_FAILED` | 500 | 原视频自带字幕提取失败 |
## VISION-R1 Keyframe APIs

VISION-R1 adds low-cost keyframe candidate access for an existing analysis task. These APIs require the same Bearer access token as task result APIs, validate `taskId + current user`, and never return `objectKey`, local filesystem paths, tokens, API keys, raw prompts, or raw model responses.

### GET /api/tasks/{taskId}/keyframes

Returns keyframe metadata selected from video frame changes. The list is ordered by `timestampMillis`.

Response data item:

| Field | Type | Description |
| --- | --- | --- |
| `frameId` | number | Public keyframe id used only for image download. |
| `timestampMillis` | number | Video timestamp in milliseconds. |
| `timeText` | string | Display timestamp such as `00:12.345`. |
| `imageUrl` | string | Authenticated API path for the thumbnail image. |
| `changeScore` | number | Normalized change score. |
| `selectReason` | string | `FIRST_FRAME`, `PERIODIC_ANCHOR`, `SCENE_CHANGE`, or `CONTENT_CHANGE`. |
| `createdAt` | string | Persisted metadata creation time. |
| `ocr` | object | Safe OCR view for this keyframe. It contains `status`, `text`, `provider`, `languageHint`, `confidence`, `truncated`, and `message`; it never contains `objectKey`, local paths, tokens, API keys, or provider stderr. |
| `visualAnalysis` | object | Safe VLM-R1 visual analysis view for this keyframe. It contains `status`, `screenType`, `summary`, `detectedElements`, `provider`, `model`, and `message`; it never contains `objectKey`, local paths, API keys, provider stderr, raw requests, or raw responses. |

OCR statuses:

| Status | Meaning |
| --- | --- |
| `PENDING` | OCR is enabled but no OCR row is available yet. |
| `SUCCEEDED` | OCR text was recognized. |
| `EMPTY` | OCR ran but found no text. |
| `FAILED` | OCR failed for this frame; the main ASR/LLM result is still valid. |
| `SKIPPED` | The frame was skipped by OCR resource limits. |
| `DISABLED` | OCR is disabled by runtime configuration. |

Visual analysis statuses:

| Status | Meaning |
| --- | --- |
| `PENDING` | Visual analysis is enabled but no analysis row is available yet. |
| `SUCCEEDED` | A concise screen summary was generated for this frame. |
| `EMPTY` | The provider ran but returned no useful visual description. |
| `FAILED` | Visual analysis failed for this frame; the main ASR/LLM result is still valid. |
| `SKIPPED` | The frame was skipped by high-value frame limits. |
| `DISABLED` | Visual analysis is disabled by runtime configuration. |

`screenType` is a safe label such as `PPT`, `CODE`, `TERMINAL`, `WHITEBOARD`, `BROWSER`, or `OTHER`. Visual analysis is disabled by default and only runs for bounded high-value keyframes when `COURSELINGO_VISION_ANALYSIS_ENABLED=true`.

### GET /api/tasks/{taskId}/keyframes/{frameId}/image

Streams the selected thumbnail image as `image/jpeg`. The backend resolves the internal storage object only after owner-scope validation. Frontend clients must request this endpoint with authenticated axios/fetch and create a temporary object URL; the object URL should be revoked when the task changes or the page unloads.

### GET /api/tasks/{taskId}/results

The result response now includes `keyframes: VideoKeyframeView[]` with the same safe metadata fields as `GET /api/tasks/{taskId}/keyframes`, including nested safe `ocr` and `visualAnalysis` metadata. FUSION-R1 also adds `videoSegments: VideoSegmentResponse[]`, read from the same safe owner-scoped view as `GET /api/tasks/{taskId}/video-segments`. It still does not expose `userId`, `objectKey`, local paths, API credentials, provider stderr, raw requests, or raw AI payloads.

## FUSION-R1 Video Segment APIs

FUSION-R1 adds rule-based ASR + OCR + visual-summary segment evidence. It is disabled by default, does not call LLMs by default, and does not implement course QA or embeddings.

### GET /api/tasks/{taskId}/video-segments

Returns the current user's safe video segment evidence for a task. The backend validates `Authorization: Bearer <accessToken>` and `taskId + current user`; client-provided `userId` is ignored.

Query parameters:

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `limit` | number | `100` | Maximum rows returned, capped by the server. |
| `offset` | number | `0` | Zero-based offset after optional filtering. |
| `keyword` | string | empty | Optional filter over time text, summary, ASR, OCR, visual summary, and keywords. |

Response data item:

| Field | Type | Description |
| --- | --- | --- |
| `segmentId` | number | Public segment row id. |
| `segmentIndex` | number | Zero-based segment window index. |
| `startMillis` / `endMillis` | number | Segment time range. |
| `timeText` | string | Display range such as `00:00:00 - 00:01:00`. |
| `asrText` | string | Bounded transcript evidence for the window. |
| `ocrText` | string | Bounded OCR evidence for matching keyframes. |
| `visualSummary` | string | Bounded VLM summary evidence when historical VLM rows exist. |
| `fusedSummary` | string | Rule-generated Chinese summary; no LLM is called in FUSION-R1. |
| `keywords` | string[] | Rule-extracted keywords. |
| `evidence` | object | Evidence id lists and source counts. |
| `status` | string | `SUCCEEDED`, `EMPTY`, `FAILED`, `SKIPPED`, or `DISABLED`. |
| `confidence` | number | Lightweight source-count confidence score. |

The API never returns `objectKey`, local paths, raw prompts, raw responses, provider stderr, API keys, tokens, database passwords, or `userId`.

### POST /api/tasks/{taskId}/video-segments/rebuild

Rebuilds only the persisted `video_segment` rows for one existing task. The endpoint requires `Authorization: Bearer <accessToken>`, resolves the current user on the server, and loads the task by `taskId + userId`. A missing or non-owner task returns `TASK_NOT_FOUND`; a task whose status is not `SUCCEEDED` returns `TASK_INVALID_STATUS`.

The rebuild reuses the existing rule-based fusion core in one transaction: it deletes the current task's segment rows and regenerates them from persisted subtitles, keyframes, OCR, and existing visual-analysis facts. The explicit repair endpoint runs even when automatic pipeline fusion is disabled; the disabled flag continues to suppress only the automatic `fuse(taskId, userId)` pipeline entry. It does not create an analysis task, run ASR or translation, call an LLM, write `ai_call_record`, change upload data, or change `analysis_task.status`.

Successful response data is limited to safe counters:

| Field | Type | Description |
| --- | --- | --- |
| `windows` | number | Total bounded windows derived from the media evidence duration. |
| `saved` | number | Non-empty segment rows persisted. |
| `empty` | number | Windows with no usable evidence. |
| `skipped` | number | Windows omitted by the configured maximum segment count. |

For a non-integral final window, persisted `endMillis` is `min(startMillis + windowMillis, durationMillis)`. Windows with `endMillis <= startMillis` are not created, and all ASR/OCR/keyframe/visual evidence selection and persisted time text use the clamped range.

## QA-R1 course QA API

### POST /api/tasks/{taskId}/qa

Creates one non-streaming course-scoped QA answer for the current authenticated user. The backend validates `Authorization: Bearer <accessToken>` and checks `taskId + current user`; client-provided owner fields are ignored.

Request body:

```json
{
  "question": "老师在 00:03:00 到 00:05:00 讲了什么？"
}
```

Validation:

- `question` is trimmed, must be non-empty, and is limited by `COURSELINGO_QA_QUESTION_MAX_LENGTH` with a default of 500 characters.
- The endpoint is single-turn and single-task only; it does not search other videos, use embeddings, create a vector database record, or keep chat memory.
- Redis rate limiting uses `COURSELINGO_QA_RATE_LIMIT_PER_MINUTE`, defaulting to 10 requests per minute.

Response data:

| Field | Type | Description |
| --- | --- | --- |
| `recordId` | string | Safe QA record id returned to the client. |
| `answer` | string | Chinese answer grounded in the selected evidence, or `当前课程内容中没有找到明确依据` when evidence is insufficient. |
| `evidence` | array | Time-bounded evidence cards used by the answer. |
| `usage` | object | Safe provider/model/token/duration summary when an LLM call was made. |

Evidence item:

| Field | Type | Description |
| --- | --- | --- |
| `sourceType` | string | `VIDEO_SEGMENT`, `SUBTITLE_TRANSLATION`, or `SUBTITLE`. QA-R1 does not use OCR as default question-answering evidence. |
| `sourceId` | string | Safe source row id. |
| `startTimeMillis` / `endTimeMillis` | number | Evidence time range. |
| `timeText` | string | Display range such as `00:03:00 - 00:05:00`. |
| `snippet` | string | Bounded original evidence text. |
| `translatedSnippet` | string | Bounded translated or fused evidence text when available. |
| `confidence` | number | Lightweight retrieval confidence score. |

QA-R1 evidence is primarily built from ASR transcript text, subtitle translations, source subtitles, and time-bounded video segment speech evidence. OCR and keyframe data remain experimental visual assistance elsewhere in the product, but OCR is not included in QA-R1 prompt evidence, response evidence, or `course_qa_record.evidence_json` by default. The endpoint does not return object keys, local paths, raw prompts, raw provider responses, API keys, tokens, database passwords, JWT secrets, or user ids. If no usable course evidence exists, the backend records the insufficient result and does not call the LLM.

Query terms are extracted by `CourseQaQueryTermExtractor`. It splits Chinese/Latin transitions, normalizes technical identifiers case-insensitively while preserving letters, digits, `+`, `#`, `.`, `_`, and `-`, and treats bounded Chinese and English question phrases as separators. Generic questions alone cannot create relevance. Candidate scoring remains `relevanceScore = keywordScore + timeBoost`; source weight and confidence are applied only after positive relevance.

The insufficient-evidence answer has one exact constant source, `CourseQaMessages.INSUFFICIENT_EVIDENCE`, whose decoded value is `当前课程内容中没有找到明确依据` with no punctuation, surrounding whitespace, prefix, suffix, or line break. Empty retrieval returns that answer with `evidence = []` and `usage = null`, without starting an LLM or QA `ai_call_record`. A completed model call that cites no valid evidence returns the same exact answer and empty evidence while retaining the completed call audit.

## CHAPTER-R1 course chapter timeline API

CHAPTER-R1 adds on-demand course chapter generation for one existing analysis task. It is not a new pipeline step: opening the result page does not call an LLM, and the main ASR / translation / learning-package task status is not changed by chapter generation.

### GET /api/tasks/{taskId}/chapters

Returns persisted chapters for the current authenticated user and task. The backend validates `Authorization: Bearer <accessToken>` and checks `taskId + current user`; client-provided owner fields are ignored. The endpoint does not call LLMs and returns an empty list when no chapters have been generated.

Response data item:

| Field | Type | Description |
| --- | --- | --- |
| `id` | number | Safe chapter row id. |
| `chapterIndex` | number | Zero-based chapter order. |
| `title` | string | Chinese chapter title. |
| `summary` | string | One-sentence Chinese chapter summary. |
| `keywords` | string[] | Bounded chapter keywords. |
| `startTimeMillis` / `endTimeMillis` | number | Chapter time range, clamped to evidence windows. |
| `timeText` | string | Display range such as `00:00:00 - 00:04:00`. |
| `evidence` | array | Time-window evidence used for this chapter. |
| `usage` | object | Safe provider/model/token/duration summary persisted with the generated chapter. |

### POST /api/tasks/{taskId}/chapters/generate

Synchronously generates chapters for the current authenticated user's task and persists them in `course_chapter`. On success, existing chapters for the same `taskId + userId` are overwritten. On parse/provider failure, the original task state is not changed and existing chapters are preserved.

Generation evidence is built from stable text timelines only:

- `subtitle_segment`;
- `subtitle_translation_segment` when available;
- `video_segment.asr_text`;
- `learning_package.summary` and glossary only as global auxiliary context, never as chapter time boundaries.

CHAPTER-R1 does not use OCR, keyframes, VLM, embeddings, a vector database, Agent behavior, cross-course search, streaming responses, or multi-turn memory. The prompt asks the LLM for JSON only:

```json
{
  "chapters": [
    {
      "title": "什么是大语言模型",
      "summary": "本章介绍大语言模型的基本概念。",
      "startTimeMillis": 0,
      "endTimeMillis": 180000,
      "keywords": ["语言模型", "上下文窗口"],
      "evidenceIndexes": [0, 1]
    }
  ]
}
```

The backend filters out-of-range `evidenceIndexes`, clamps chapter times to evidence ranges, sorts chapters by start time, drops invalid duplicates/overlaps, limits chapter count, writes `ai_call_record` with stage `COURSE_CHAPTER`, and never persists or returns raw prompts, raw provider responses, object keys, local paths, API keys, tokens, passwords, JWT secrets, or user ids.

## PRODUCT-POLISH-R1 batch delete API

### POST /api/tasks/batch-delete

Requires `Authorization: Bearer <accessToken>`. The request body contains only task IDs:

```json
{
  "taskIds": ["task_xxx", "task_yyy"]
}
```

`taskIds` must be non-null, contain 1–100 raw entries, contain no null/blank entry, and each ID must be at most 64 characters. The service trims and deduplicates IDs while preserving request order; `requestedCount` is the final unique count.

Only `SUCCEEDED`, `FAILED`, and `CANCELED` tasks may be deleted. Any non-terminal or unknown status rejects the whole request with HTTP 409 `TASK_DELETE_NOT_ALLOWED` and message `存在仍在处理中的课程，请先取消处理后再删除`. A missing task or task owned by another user rejects the whole request with HTTP 404 `TASK_NOT_FOUND`. Invalid input uses HTTP 400 `COMMON_VALIDATION_FAILED`.

Success response data:

```json
{
  "requestedCount": 2,
  "deletedCount": 2
}
```

The operation is idempotent: tasks already soft-deleted by the same user still satisfy ownership validation but are ignored by the update. A fully repeated request returns `deletedCount: 0`. The transactional update is one batch SQL statement scoped by `user_id`, the unique ID set, `deleted_at IS NULL`, and the allowed status set. It updates only `deleted_at` and `updated_at`; it does not delete associated rows, MinIO objects, Redis state, MQ messages, or artifacts.

After deletion, all public task paths treat the task as missing, including list/detail, retry/cancel, result, playback token, embedded subtitles, artifact, keyframe image, chapters, QA, Video Segment, video context, and SSE.

## VIDEO-CONTEXT-R1 course video context API

VIDEO-CONTEXT-R1 adds a backend fixed-window context index for one existing analysis task. It is not connected to the main Pipeline, QA, or Chapter generation in R1. It does not call an LLM, does not write `ai_call_record`, does not use OCR, keyframes, VLM, Agent behavior, embeddings, or a vector database.

### GET /api/tasks/{taskId}/video-context

Returns persisted video-context chunks for the current authenticated user and task. The backend validates `Authorization: Bearer <accessToken>` and checks `taskId + current user`; client-provided owner fields are ignored. GET does not rebuild chunks and does not call any model.

Response data:

| Field | Type | Description |
| --- | --- | --- |
| `taskId` | string | Analysis task id. |
| `targetLanguage` | string | Task target language. |
| `durationMillis` | number | Maximum persisted chunk end time. |
| `chunkWindowSeconds` | number | Effective chunk window size. |
| `buildVersion` | string | `VIDEO_CONTEXT_R1`. |
| `sourceStats` | object | Safe counts for subtitles, translations, chapters, chunks, learning package, and ASR segment presence. |
| `globalSummary` | string | Rule-selected global summary, mainly from `learning_package.summary`. |
| `globalKeywords` | string[] | Rule-selected global keywords, mainly from learning-package glossary. |
| `chapters` | array | Existing semantic chapter metadata plus covered chunk indexes. |
| `chunks` | array | Persisted fixed-window chunks. |

Chunk item:

| Field | Type | Description |
| --- | --- | --- |
| `chunkIndex` | number | Zero-based fixed-window chunk index. |
| `startMillis` / `endMillis` | number | Chunk time range. |
| `timeText` | string | Display range such as `00:00:00 - 00:04:00`. |
| `summary` | string | Rule-generated summary. It prefers translated subtitle excerpts and may blend existing chapter title/summary. |
| `keywords` | string[] | Rule-extracted keywords. |
| `sourceTextPreview` | string | Bounded source subtitle preview plus `video_segment.asrText` supplement. |
| `translatedTextPreview` | string | Bounded translated subtitle preview when available. |
| `evidence` | array | Bounded subtitle references with `segmentIndex`, start/end time, and safe previews. |

### POST /api/tasks/{taskId}/video-context/rebuild

Rebuilds fixed-window chunks for the current authenticated user and task. The service builds all chunks in memory first; only after a successful build does it delete old `course_video_chunk` rows for the same `taskId + userId + targetLanguage` and insert the new rows. Build failure preserves existing chunks and does not change `analysis_task.status`.

R1 source boundaries:

- uses `subtitle_translation_segment` as preferred context;
- falls back to `subtitle_segment`;
- uses existing `course_chapter` only to enrich summaries, keywords, and covered chunk indexes;
- uses `learning_package.summary` and glossary for global summary/keywords;
- uses only `video_segment.asr_text` as supplemental speech text;
- treats `task_full_text_result` only as fallback/stats context, not as full text to stuff into a chunk.

VIDEO-CONTEXT-R1 deliberately does not use OCR text, keyframe metadata, VLM output, QA history, object keys, local file paths, raw prompts, or raw provider responses. A chunk is a fixed time-window index for backend context organization; a chapter is a semantic timeline item generated separately by CHAPTER-R1.
