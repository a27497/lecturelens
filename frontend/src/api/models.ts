import { http } from "./http";
import { authHeader } from "./authToken";
import type { ApiResponse } from "../types/task";

export interface ModelCheck { ok: boolean; code: string | null; latency_ms: number; checked_at: number; version: number }
export interface ModelConnection {
  connection_id: string; name: string; base_url: string; model_ids: string[];
  enabled: boolean; version: number; has_key: boolean; checks: Record<string, ModelCheck>;
}
export interface ModelDiscovery {
  model_ids: string[]; total_count?: number; truncated?: boolean; limit?: number;
  skipped_count?: number; provider_has_more?: boolean;
}
export interface ModelBinding { connection_id?: string | null; model?: string | null }
export interface ModelPreset {
  id: string; name: string; group: string; base_url: string;
  models: string[]; note: string; docs_url: string;
}
export interface ModelCatalog {
  presets?: ModelPreset[];
  presets_checked_at?: string;
  connections: ModelConnection[];
  bindings: { decision: ModelBinding; review: ModelBinding };
  environment: { available: boolean; model: string; mode: string };
}
export async function modelCommand<T = ModelCatalog>(command: Record<string, unknown>): Promise<T> {
  const response = await http.post<ApiResponse<T>>("/api/agent/models/command", command, { headers: authHeader() });
  return response.data.data;
}
const messages: Record<string, string> = {
  MODEL_MANAGEMENT_DISABLED: "模型管理尚未启用，请先启用学习助手服务。",
  MODEL_MANAGEMENT_UNAVAILABLE: "模型管理服务暂不可用，请稍后重试。",
  MODEL_ORIGIN_NOT_ALLOWED: "此服务地址尚未开放，请由部署管理员加入允许的模型服务地址。",
  MODEL_BASE_URL_INVALID: "请输入正确的服务基础地址，不包含密钥、查询参数或账号信息。",
  MODEL_KEY_REQUIRED_FOR_NEW_URL: "服务地址已改变，请重新输入密钥，或勾选清除密钥。",
  MODEL_CREDENTIAL_INVALID: "密钥格式不正确，请检查后重试。",
  MODEL_VERSION_CONFLICT: "连接已在其他页面修改，请刷新后重新操作。",
  MODEL_CONNECTION_IN_USE: "请先将 Agent 的模型用途切换到其他连接，再删除此连接。",
  MODEL_CONNECTION_NOT_FOUND: "连接已不存在，请刷新列表。",
  MODEL_BINDING_UNAVAILABLE: "所选连接已停用，或模型不在已保存列表中，请重新选择。",
  MODEL_ROUTE_REQUIRED: "请先为 Agent 决策与草稿复核选择模型。",
  MODEL_AUTH_FAILED: "模型服务拒绝了密钥或模型权限，请检查 Key、地域及模型开通状态。",
  MODEL_RATE_LIMITED: "模型服务限流或额度受限，请检查服务商控制台后稍后重试。",
  MODEL_UNAVAILABLE: "暂时无法连接模型服务，请稍后重试。",
  MODEL_REQUEST_REJECTED: "模型服务不接受当前请求，请检查所选模型和接口参数兼容性。",
  MODEL_REVIEW_CONTRACT: "复核模型返回的结论格式不符合要求，本次未保存产物；请更换复核模型或检查兼容性。",
  MODEL_TOOL_CONTRACT: "模型未返回符合要求的工具调用，本次已停止；可更换模型后重试。",
  MODEL_INVALID_RESPONSE: "模型服务返回格式异常，本次已停止。",
  MODEL_OUTPUT_TRUNCATED: "模型输出达到上限，草稿未完整返回；请缩小学习目标后重试。",
  MODEL_TIMEOUT: "模型响应超时，请稍后重试或更换模型。",
  MODEL_CHECK_FAILED: "连接测试失败，请检查地址、密钥、模型 ID 和工具调用支持。",
  MODEL_CHECK_TIMEOUT: "连接测试超时，请检查服务响应速度。",
  MODEL_CHECK_BUSY: "正在进行其他连接测试，请稍后重试。",
  MODEL_CREDENTIAL_UNAVAILABLE: "已保存凭据无法解密，请检查服务端加密密钥。",
  MODEL_CONFIGURATION_INVALID: "配置格式不正确，请检查模型 ID、地址和必填项。",
  MODEL_CONNECTION_LIMIT: "最多可保存 20 个连接，请先删除不再使用的连接。",
};
export function modelError(error: unknown, fallback = "操作未完成，请检查配置或稍后重试。"): string {
  const response = (error as { response?: { data?: { message?: string } } })?.response;
  const code = response?.data?.message ?? (error instanceof Error ? error.message : "");
  return messages[code] ?? fallback;
}
