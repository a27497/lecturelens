import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AdminModelManagementView from "./AdminModelManagementView.vue";
import { systemModels, type SystemCatalog, type SystemStatus, type ProbePolicy, type SystemVersion } from "../api/systemModels";
import { useAuthStore } from "../stores/auth";
import { modelCommand } from "../api/models";

vi.mock("../api/systemModels", async original => {
  const actual = await original<typeof import("../api/systemModels")>();
  return { ...actual, systemModels: Object.fromEntries(Object.keys(actual.systemModels).map(key => [key, vi.fn()])) };
});
vi.mock("../api/models", () => ({ modelCommand: vi.fn() }));
const routes = {
  TRANSLATION_FULL_TEXT: { feature: "TRANSLATION_FULL_TEXT", source: "DATABASE", protocol: "OPENAI_CHAT" as const, providerId: 10, modelId: 100, baseUrl: "https://api.deepseek.com", model: "deepseek-chat", hasKey: true, keyLast4: "1234" },
  COURSE_QA: { feature: "COURSE_QA", source: "ENV", protocol: "OPENAI_CHAT" as const, providerId: null, modelId: null, baseUrl: "https://legacy.example/v1", model: "legacy", hasKey: true, keyLast4: "5678" },
  ASR_TRANSCRIPTION: { feature: "ASR_TRANSCRIPTION", source: "MOCK", protocol: null, providerId: null, modelId: null, baseUrl: null, model: null, hasKey: false, keyLast4: null },
};
const base: SystemCatalog = {
  version: 7, fullTextTranslation: true,
  providers: [{ id: 10, name: "全文翻译供应商", protocol: "OPENAI_CHAT", baseUrl: "https://api.deepseek.com", enabled: true, hasKey: true, keyLast4: "1234" },
    { id: 20, name: "转写供应商", protocol: "SILICONFLOW_ASR", baseUrl: "https://silicon.example", enabled: true, hasKey: true, keyLast4: "9876" }],
  models: [{ id: 100, providerId: 10, model: "deepseek-chat", capabilities: ["TEXT_CHAT", "JSON_OUTPUT"], parameters: {}, enabled: true },
    { id: 101, providerId: 10, model: "other-text", capabilities: ["TEXT_CHAT", "JSON_OUTPUT"], parameters: {}, enabled: true },
    { id: 200, providerId: 20, model: "asr-model", capabilities: ["ASR"], parameters: {}, enabled: true }],
  bindings: { TRANSLATION_FULL_TEXT: 100 }, effective: routes,
};
const status: SystemStatus = { version: 7, features: [
  { key: "TRANSLATION_FULL_TEXT", connected: true, active: true, source: "DATABASE", version: 7, finalUrl: "https://api.deepseek.com/chat/completions", configurationStatus: "READY" },
  { key: "COURSE_QA", connected: true, active: true, source: "ENV", version: 7, finalUrl: "https://legacy.example/v1/chat/completions", configurationStatus: "READY" },
  { key: "ASR_TRANSCRIPTION", connected: true, active: true, source: "MOCK", version: 7, finalUrl: null, configurationStatus: "MOCK" },
  { key: "FUSION_SUMMARY", connected: false, active: false, source: "UNCONNECTED", version: 7, finalUrl: null, configurationStatus: "UNCONNECTED" },
] };
const policy: ProbePolicy = { allowedOrigins: ["https://api.deepseek.com"], timeoutMillis: 10000, concurrency: 2, responseLimitBytes: 65536, asrFixtureSha256: "fixture-hash" };
let wrapper: ReturnType<typeof mount> | undefined;
let auth: ReturnType<typeof useAuthStore>;
function render() { wrapper = mount(AdminModelManagementView, { global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } } }); return wrapper; }
beforeEach(() => {
  vi.resetAllMocks(); setActivePinia(createPinia()); auth = useAuthStore();
  auth.$patch({ accessToken: "test-token", user: { userId: 1, email: "admin@example.invalid", status: "ACTIVE", role: "ADMIN" } });
  vi.mocked(systemModels.catalog).mockResolvedValue(structuredClone(base));
  vi.mocked(systemModels.status).mockImplementation(async version => ({ ...structuredClone(status), version, features: status.features.map(f => ({ ...f, version })) }));
  vi.mocked(systemModels.policy).mockResolvedValue(structuredClone(policy));
  vi.mocked(systemModels.versions).mockResolvedValue([{ version: 3, parentVersion: 2, actorUserId: 1, reason: "BINDINGS_UPDATED", createdAt: "2026-10-15" }]);
  vi.mocked(systemModels.audit).mockResolvedValue([]);
});
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); });

it("shows actual sources, local validity, masks, versions and final URLs without automatic probes or Agent commands", async () => {
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const page = render(); await flushPromises();
  expect(page.get('[data-feature="TRANSLATION_FULL_TEXT"]').text()).toContain("数据库绑定");
  expect(page.get('[data-feature="TRANSLATION_FULL_TEXT"]').text()).toContain("https://api.deepseek.com/chat/completions");
  expect(page.get('[data-feature="COURSE_QA"]').text()).toContain("部署默认");
  expect(page.get('[data-feature="ASR_TRANSCRIPTION"]').text()).toContain("显式 Mock");
  expect(page.get('[data-feature="FUSION_SUMMARY"]').find("select").exists()).toBe(false);
  expect(page.text()).toContain("配置可解析"); expect(page.text()).toContain("当前版本尚未测试");
  expect(page.text()).toContain("••••1234"); expect(page.text()).toContain("当前配置版本 7");
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
  expect(systemModels.probe).not.toHaveBeenCalled(); expect(modelCommand).not.toHaveBeenCalled();
  expect(storage).not.toHaveBeenCalled();
});

it("does not load administrator data when mounted by an ordinary user", async () => {
  auth.user!.role = "USER"; const page = render(); await flushPromises();
  expect(page.text()).toContain("需要管理员权限");
  expect(systemModels.catalog).not.toHaveBeenCalled(); expect(systemModels.probe).not.toHaveBeenCalled();
});

it("saves a key only to the provider API, clears it immediately and shows only the mask on reload", async () => {
  const page = render(); await flushPromises();
  const storage = vi.spyOn(Storage.prototype, "setItem");
  await page.get('[aria-label="编辑供应商"]').setValue("10");
  await page.get<HTMLInputElement>('input[type="password"]').setValue("typed-system-secret");
  let sent: unknown;
  vi.mocked(systemModels.saveProvider).mockImplementationOnce(async (_id, data) => {
    sent = structuredClone(data); return { ...structuredClone(base), version: 8 };
  });
  await page.get('form[aria-label="供应商设置"]').trigger("submit");
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
  await flushPromises();
  expect(sent).toMatchObject({ expectedVersion: 7, apiKey: "typed-system-secret", clearKey: false });
  expect(page.text()).not.toContain("typed-system-secret");
  expect(storage).not.toHaveBeenCalled();
  await page.findAll("button").find(b => b.text() === "刷新配置")!.trigger("click"); await flushPromises();
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
  expect(page.text()).toContain("••••1234");
});

it("omits a blank key and clears a rejected key while retaining nonsecret conflict edits", async () => {
  const page = render(); await flushPromises();
  await page.get('[aria-label="编辑供应商"]').setValue("10");
  vi.mocked(systemModels.saveProvider).mockResolvedValueOnce({ ...base, version: 8 });
  await page.get('form[aria-label="供应商设置"]').trigger("submit"); await flushPromises();
  expect(vi.mocked(systemModels.saveProvider).mock.calls[0]![1]).not.toHaveProperty("apiKey");
  await page.get<HTMLInputElement>('input[type="url"]').setValue("https://new.example");
  await page.get<HTMLInputElement>('input[type="password"]').setValue("secret-after-conflict");
  vi.mocked(systemModels.saveProvider).mockRejectedValueOnce({ response: { data: { code: "SYSTEM_MODEL_CONFIG_CONFLICT", message: "secret-after-conflict" } } });
  await page.get('form[aria-label="供应商设置"]').trigger("submit"); await flushPromises();
  expect(page.get('[role="alert"]').text()).toContain("其他页面修改");
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
  expect(page.get<HTMLInputElement>('input[type="url"]').element.value).toBe("https://new.example");
  expect(page.text()).not.toContain("secret-after-conflict");
});

it("clears keys on provider changes, pagehide, privilege revocation and unmount during a save", async () => {
  const page = render(); await flushPromises();
  await page.get<HTMLInputElement>('input[type="password"]').setValue("first-draft-key");
  await page.get('[aria-label="编辑供应商"]').setValue("10");
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
  await page.get<HTMLInputElement>('input[type="password"]').setValue("second-draft-key");
  window.dispatchEvent(new Event("pagehide")); await flushPromises();
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
  let finish!: (value: SystemCatalog) => void;
  vi.mocked(systemModels.saveProvider).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  await page.get<HTMLInputElement>('input[type="password"]').setValue("pending-draft-key");
  await page.get('form[aria-label="供应商设置"]').trigger("submit");
  page.unmount(); wrapper = undefined;
  finish({ ...base, version: 8 }); await flushPromises();
  expect(vi.mocked(systemModels.saveProvider).mock.calls[0]![1]).not.toHaveProperty("apiKey");
  const revoked = render(); await flushPromises();
  await revoked.get<HTMLInputElement>('input[type="password"]').setValue("revoked-draft-key");
  auth.user!.role = "USER"; await flushPromises();
  expect(revoked.find('input[type="password"]').exists()).toBe(false);
  expect(revoked.text()).not.toContain("revoked-draft-key");
});

it("saves only changed system feature bindings with expectedVersion and leaves Agent decision/review untouched", async () => {
  const page = render(); await flushPromises();
  await page.get('[aria-label="字幕全文翻译绑定"]').setValue("101");
  vi.mocked(systemModels.bindings).mockResolvedValueOnce({ ...structuredClone(base), version: 8, bindings: { TRANSLATION_FULL_TEXT: 101 } });
  await page.findAll("button").find(b => b.text() === "保存功能绑定")!.trigger("click"); await flushPromises();
  expect(systemModels.bindings).toHaveBeenCalledExactlyOnceWith(7, { TRANSLATION_FULL_TEXT: 101 });
  expect(systemModels.probe).not.toHaveBeenCalled(); expect(modelCommand).not.toHaveBeenCalled();
  const asrOptions = page.get('[aria-label="语音转写绑定"]').findAll("option").map(o => o.attributes("value"));
  expect(asrOptions).toContain("200"); expect(asrOptions).not.toContain("100");
});

it("sends numeric model parameters correctly after number inputs", async () => {
  const page = render(); await flushPromises();
  await page.get('[aria-label="编辑模型"]').setValue("100");
  const numbers = page.findAll('form[aria-label="模型设置"] input[type="number"]');
  await numbers[0]!.setValue("0.5"); await numbers[2]!.setValue("5000");
  vi.mocked(systemModels.saveModel).mockResolvedValueOnce({ ...structuredClone(base), version: 8 });
  await page.get('form[aria-label="模型设置"]').trigger("submit"); await flushPromises();
  expect(systemModels.saveModel).toHaveBeenCalledWith(100, 10, expect.objectContaining({ expectedVersion: 7, parameters: { temperature: 0.5, maxTokens: null, timeoutMillis: 5000, maxAttempts: null } }));
});

it("tests a saved model only on click and discards its result after a new version", async () => {
  const page = render(); await flushPromises();
  await page.get<HTMLInputElement>('input[type="password"]').setValue("unsaved-private-key");
  vi.mocked(systemModels.probe).mockResolvedValueOnce({ ok: true, category: "OK", elapsedMillis: 12, version: 7, modelId: 100, finalUrl: "https://api.deepseek.com/chat/completions" });
  await page.get('[data-model="100"] button').trigger("click"); await flushPromises();
  expect(systemModels.probe).toHaveBeenCalledExactlyOnceWith(7, 100);
  expect(page.get('[data-model="100"]').text()).toContain("通过 · 12 毫秒 · 版本 7");
  expect(page.get('[data-model="100"]').text()).not.toContain("unsaved-private-key");
  vi.mocked(systemModels.catalog).mockResolvedValueOnce({ ...structuredClone(base), version: 8 });
  await page.findAll("button").find(b => b.text() === "刷新配置")!.trigger("click"); await flushPromises();
  expect(page.get('[data-model="100"]').text()).toContain("当前版本尚未测试");
  expect(page.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
});

it("disables tests when no deployment origin is allowed and displays safe failure categories", async () => {
  vi.mocked(systemModels.policy).mockResolvedValueOnce({ ...policy, allowedOrigins: [] });
  const page = render(); await flushPromises();
  expect(page.get('[data-model="100"] button').attributes("disabled")).toBeDefined();
  expect(systemModels.probe).not.toHaveBeenCalled();
  vi.mocked(systemModels.policy).mockResolvedValueOnce(policy);
  await page.findAll("button").find(b => b.text() === "刷新配置")!.trigger("click"); await flushPromises();
  vi.mocked(systemModels.probe).mockResolvedValueOnce({ ok: false, category: "AUTHENTICATION", elapsedMillis: 8, version: 7, modelId: 100, finalUrl: "https://api.deepseek.com/chat/completions" });
  await page.get('[data-model="100"] button').trigger("click"); await flushPromises();
  expect(page.get('[data-model="100"]').text()).toContain("认证失败");
});

it("renders masked history and explicitly restores only the selected feature binding", async () => {
  const page = render(); await flushPromises();
  const historical = { version: 3, parentVersion: 2, actorUserId: 1, reason: "OLD", createdAt: "2026", config: { ...structuredClone(base), ciphertext: "forbidden-history-cipher" } } as SystemVersion;
  vi.mocked(systemModels.version).mockResolvedValueOnce(historical);
  await page.get('[aria-label="历史版本"]').setValue("3");
  await page.findAll("button").find(b => b.text() === "查看历史配置")!.trigger("click"); await flushPromises();
  expect(page.get('[data-testid="history"]').text()).toContain("••••1234");
  expect(page.html()).not.toContain("forbidden-history-cipher");
  await page.get('[aria-label="恢复的功能"]').setValue("ASR_TRANSCRIPTION");
  vi.mocked(systemModels.rollback).mockResolvedValueOnce({ ...structuredClone(base), version: 8 });
  await page.findAll("button").find(b => b.text() === "恢复该功能到所选版本的绑定")!.trigger("click"); await flushPromises();
  expect(systemModels.rollback).toHaveBeenCalledExactlyOnceWith(7, "ASR_TRANSCRIPTION", 3);
});

it("queries snapshots by task ID and displays decryption failures without sending a probe", async () => {
  vi.mocked(systemModels.status).mockResolvedValueOnce({ ...status, features: status.features.map(f => f.key === "TRANSLATION_FULL_TEXT" ? { ...f, configurationStatus: "KEY_UNAVAILABLE" } : f) });
  const page = render(); await flushPromises();
  expect(page.get('[data-feature="TRANSLATION_FULL_TEXT"]').text()).toContain("密钥无法解密");
  vi.mocked(systemModels.executions).mockResolvedValueOnce([{ id: "snapshot-A", taskId: "task-A", operationType: "PIPELINE", configVersion: 4, origin: "CREATED", routes, createdAt: "2026" }]);
  await page.get('[aria-label="任务 ID"]').setValue("task-A");
  await page.get('form[aria-label="查询执行快照"]').trigger("submit"); await flushPromises();
  expect(systemModels.executions).toHaveBeenCalledExactlyOnceWith("task-A");
  expect(page.text()).toContain("snapshot-A"); expect(page.text()).toContain("版本 4");
  expect(systemModels.probe).not.toHaveBeenCalled();
});

it("removes administrator data and clears the key when the backend revokes access", async () => {
  const page = render(); await flushPromises();
  await page.get<HTMLInputElement>('input[type="password"]').setValue("revoked-at-api-key");
  vi.mocked(systemModels.probe).mockRejectedValueOnce({ response: { status: 403, data: { code: "COMMON_FORBIDDEN" } } });
  await page.get('[data-model="100"] button').trigger("click"); await flushPromises();
  expect(auth.isAdmin).toBe(false);
  expect(page.find('input[type="password"]').exists()).toBe(false);
  expect(page.text()).not.toContain("deepseek-chat");
  expect(page.text()).not.toContain("revoked-at-api-key");
  expect(page.text()).toContain("需要管理员权限");
});
