import { http } from "./http";
import { authHeader } from "./authToken";
import type { ApiResponse } from "./auth";

export type Protocol = "OPENAI_CHAT" | "BAILIAN_ASR" | "SILICONFLOW_ASR";
export interface SystemProvider {
  id: number; name: string; protocol: Protocol; baseUrl: string; enabled: boolean;
  hasKey: boolean; keyLast4: string | null;
}
export interface ModelParameters { temperature?: number | null; maxTokens?: number | null; timeoutMillis?: number | null; maxAttempts?: number | null }
export interface SystemModel { id: number; providerId: number; model: string; capabilities: string[]; parameters: ModelParameters; enabled: boolean }
export interface SystemRoute {
  feature: string; source: string; protocol: Protocol | null; providerId: number | null; modelId: number | null;
  baseUrl: string | null; model: string | null; hasKey: boolean; keyLast4: string | null;
}
export interface SystemCatalog {
  version: number; providers: SystemProvider[]; models: SystemModel[]; bindings: Record<string, number>;
  effective: Record<string, SystemRoute>; fullTextTranslation: boolean;
}
export interface FeatureStatus {
  key: string; connected: boolean; active: boolean; source: string; version: number;
  finalUrl: string | null; configurationStatus: string;
}
export interface SystemStatus { version: number; features: FeatureStatus[] }
export interface ProbePolicy { allowedOrigins: string[]; timeoutMillis: number; concurrency: number; responseLimitBytes: number; asrFixtureSha256: string }
export interface ProbeResult { ok: boolean; category: string; elapsedMillis: number; version: number; modelId: number; finalUrl: string | null }
export interface VersionSummary { version: number; parentVersion: number | null; actorUserId: number | null; reason: string; createdAt: string }
export interface SystemVersion extends VersionSummary { config: SystemCatalog }
export interface SystemAudit { id: number; version: number | null; action: string; objectType: string; objectId: string; createdAt: string }
export interface SystemExecution { id: string; taskId: string; operationType: string; configVersion: number; origin: string; routes: Record<string, SystemRoute>; createdAt: string }

const base = "/api/admin/system-models";
async function request<T>(method: "get" | "post" | "patch" | "put" | "delete", path: string, data?: unknown): Promise<T> {
  const response = await http.request<ApiResponse<T>>({ method, url: base + path, data, headers: authHeader() });
  return response.data.data;
}
export const systemModels = {
  catalog: () => request<SystemCatalog>("get", "/catalog"),
  status: (version: number) => request<SystemStatus>("get", `/status?version=${version}`),
  policy: () => request<ProbePolicy>("get", "/probe-policy"),
  versions: () => request<VersionSummary[]>("get", "/versions"),
  version: (version: number) => request<SystemVersion>("get", `/versions/${version}`),
  audit: () => request<SystemAudit[]>("get", "/audit"),
  executions: (taskId: string) => request<SystemExecution[]>("get", `/executions?taskId=${encodeURIComponent(taskId)}`),
  saveProvider: (id: number | null, data: { expectedVersion: number; name: string; protocol: Protocol; baseUrl: string; enabled: boolean; apiKey?: string; clearKey: boolean }) =>
    request<SystemCatalog>(id === null ? "post" : "patch", id === null ? "/providers" : `/providers/${id}`, data),
  deleteProvider: (id: number, version: number) => request<SystemCatalog>("delete", `/providers/${id}?expectedVersion=${version}`),
  saveModel: (id: number | null, providerId: number, data: { expectedVersion: number; model: string; capabilities: string[]; parameters: ModelParameters; enabled: boolean }) =>
    request<SystemCatalog>(id === null ? "post" : "patch", `/providers/${providerId}/models${id === null ? "" : `/${id}`}`, data),
  deleteModel: (id: number, version: number) => request<SystemCatalog>("delete", `/models/${id}?expectedVersion=${version}`),
  bindings: (version: number, bindings: Record<string, number | null>) => request<SystemCatalog>("put", "/bindings", { expectedVersion: version, bindings }),
  bind: (version: number, feature: string, modelId: number | null) => request<SystemCatalog>("put", "/bindings", { expectedVersion: version, bindings: { [feature]: modelId } }),
  rollback: (version: number, feature: string, targetVersion: number) => request<SystemCatalog>("post", "/rollbacks", { expectedVersion: version, feature, targetVersion }),
  probe: (version: number, modelId: number) => request<ProbeResult>("post", "/probes", { expectedVersion: version, modelId }),
};

const messages: Record<string, string> = {
  COMMON_FORBIDDEN: "需要管理员权限。", COMMON_UNAUTHORIZED: "请重新登录。",
  SYSTEM_MODEL_CONFIG_CONFLICT: "配置已在其他页面修改，请刷新后重新应用更改。",
  SYSTEM_MODEL_CONFIG_UNAVAILABLE: "系统配置暂不可用，请检查服务端配置。",
  SYSTEM_MODEL_CONFIG_INVALID: "配置不正确，请检查协议、能力、地址及参数。",
  SYSTEM_MODEL_KEY_INVALID: "密钥格式不正确，请重新输入。",
  SYSTEM_MODEL_ADDRESS_FORBIDDEN: "该地址不符合公网服务地址要求。",
  SYSTEM_MODEL_DISABLED: "系统模型配置层尚未启用。",
};
export function systemModelError(error: unknown): string {
  const code = (error as { response?: { status?: number; data?: { code?: string } } })?.response;
  if (code?.status === 404) return "系统模型配置层尚未启用，或记录已不存在。";
  return messages[code?.data?.code ?? ""] ?? "操作未完成，请刷新或检查服务端配置。";
}
export const featureNames: Record<string, string> = {
  TRANSLATION_FULL_TEXT: "字幕全文翻译", SUBTITLE_TRANSLATION: "字幕逐段翻译", LEARNING_PACKAGE: "学习资料",
  COURSE_QA: "课程问答", COURSE_CHAPTER: "课程章节", VISION_FRAME_ANALYSIS: "视觉帧分析",
  ASR_TRANSCRIPTION: "语音转写", FUSION_SUMMARY: "融合摘要（未接通）",
};
export const sourceNames: Record<string, string> = { DATABASE: "数据库绑定", ENV: "部署默认", MOCK: "显式 Mock", UNCONFIGURED: "未配置", UNCONNECTED: "未接通" };
export const configurationNames: Record<string, string> = { READY: "配置可解析", MOCK: "显式 Mock", MISSING_KEY: "缺少密钥", KEY_UNAVAILABLE: "密钥无法解密", INVALID: "配置无效", UNCONFIGURED: "未配置", UNCONNECTED: "未接通" };
export const probeNames: Record<string, string> = { OK: "通过", BUSY: "测试并发已满", TIMEOUT: "测试超时", CANCELLED: "测试已中断", ORIGIN_NOT_ALLOWED: "地址未加入测试白名单", ADDRESS_FORBIDDEN: "地址不允许访问", AUTHENTICATION: "认证失败", MODEL_NOT_FOUND: "模型不可用", RATE_LIMIT: "供应商限流", SERVER_ERROR: "供应商服务异常", INVALID_REQUEST: "请求被拒绝", CONFIGURATION_INVALID: "配置无效", KEY_UNAVAILABLE: "密钥无法解密", OUTPUT_INVALID: "响应格式无效", NETWORK: "网络错误", REDIRECT_FORBIDDEN: "供应商要求重定向", RESPONSE_TOO_LARGE: "响应超过大小限制", ENCODING_UNSUPPORTED: "响应编码不支持" };
export function maskedKey(value: { hasKey: boolean; keyLast4: string | null } | undefined): string {
  return value?.hasKey ? `••••${value.keyLast4 ?? ""}` : "未设置";
}
