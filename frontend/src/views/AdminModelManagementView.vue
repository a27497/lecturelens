<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import PageHeading from "../components/ui/PageHeading.vue";
import SectionPanel from "../components/ui/SectionPanel.vue";
import StatusBadge from "../components/ui/StatusBadge.vue";
import ModelPickerOption from "../components/ModelPickerOption.vue";
import { useAuthStore } from "../stores/auth";
import {
  systemModels, systemModelError, featureNames, sourceNames, configurationNames, probeNames, maskedKey,
  type Protocol, type SystemCatalog, type SystemStatus, type ProbePolicy, type ProbeResult,
  type VersionSummary, type SystemVersion, type SystemAudit, type SystemExecution,
} from "../api/systemModels";

const auth = useAuthStore();
const catalog = ref<SystemCatalog>();
const status = ref<SystemStatus>();
const policy = ref<ProbePolicy>();
const versions = ref<VersionSummary[]>([]);
const audit = ref<SystemAudit[]>([]);
const history = ref<SystemVersion>();
const executions = ref<SystemExecution[]>([]);
const taskId = ref("");
const busy = ref(false);
const loading = ref(true);
const error = ref("");
const notice = ref("");
const probes = ref<Record<number, ProbeResult>>({});
const selectedProvider = ref("");
const selectedModel = ref("");
const selectedHistory = ref("");
const rollbackFeature = ref("TRANSLATION_FULL_TEXT");
const bindingDraft = reactive<Record<string, string>>({});
const provider = reactive({ name: "", protocol: "OPENAI_CHAT" as Protocol, baseUrl: "", apiKey: "", clearKey: false, enabled: true });
const model = reactive({ providerId: "", model: "", capabilities: ["TEXT_CHAT", "JSON_OUTPUT"], enabled: true,
  temperature: "", maxTokens: "", timeoutMillis: "", maxAttempts: "" });
const providerRecord = computed(() => catalog.value?.providers.find(p => String(p.id) === selectedProvider.value));
const connectedFeatures = computed(() => status.value?.features.filter(f => f.connected) ?? []);
const bindingChanged = computed(() => connectedFeatures.value.some(f => bindingDraft[f.key] !== String(catalog.value?.bindings[f.key] ?? "")));
const capabilities = [
  { key: "TEXT_CHAT", description: "文本对话" }, { key: "JSON_OUTPUT", description: "JSON 对象输出" },
  { key: "VISION", description: "图片消息" }, { key: "ASR", description: "语音转写" },
];
let active = true;
function clearSecret() { provider.apiKey = ""; }
function editProvider() {
  clearSecret();
  const saved = providerRecord.value;
  Object.assign(provider, { name: saved?.name ?? "", protocol: saved?.protocol ?? "OPENAI_CHAT",
    baseUrl: saved?.baseUrl ?? "", clearKey: false, enabled: saved?.enabled ?? true });
}
watch(selectedProvider, editProvider);
function editModel() {
  const saved = catalog.value?.models.find(m => String(m.id) === selectedModel.value);
  Object.assign(model, { providerId: String(saved?.providerId ?? providerRecord.value?.id ?? catalog.value?.providers[0]?.id ?? ""),
    model: saved?.model ?? "", capabilities: saved ? [...saved.capabilities] : ["TEXT_CHAT", "JSON_OUTPUT"], enabled: saved?.enabled ?? true,
    ...Object.fromEntries(["temperature", "maxTokens", "timeoutMillis", "maxAttempts"].map(k => [k,
      String(saved?.parameters?.[k as keyof typeof saved.parameters] ?? "")])) });
}
watch(selectedModel, editModel);
function toggleCapability(value: string) {
  model.capabilities = model.capabilities.includes(value) ? model.capabilities.filter(c => c !== value) : [...model.capabilities, value];
}
function providerName(id: number) { return catalog.value?.providers.find(p => p.id === id)?.name ?? `供应商 ${id}`; }
function candidates(feature: string) {
  return (catalog.value?.models ?? []).filter(m => {
    const p = catalog.value?.providers.find(p => p.id === m.providerId);
    if (!p?.enabled || !p.hasKey || !m.enabled) return false;
    if (feature === "ASR_TRANSCRIPTION") return p.protocol !== "OPENAI_CHAT" && m.capabilities.includes("ASR");
    return p.protocol === "OPENAI_CHAT" && m.capabilities.includes("JSON_OUTPUT")
      && m.capabilities.includes(feature === "VISION_FRAME_ANALYSIS" ? "VISION" : "TEXT_CHAT");
  });
}
async function applyCatalog(value: SystemCatalog) {
  if (!active || !auth.isAdmin) return;
  const changed = catalog.value?.version !== value.version;
  catalog.value = value;
  if (changed) probes.value = {};
  for (const key of Object.keys(featureNames)) bindingDraft[key] = String(value.bindings[key] ?? "");
  const [effective, newVersions, newAudit] = await Promise.all([systemModels.status(value.version), systemModels.versions(), systemModels.audit()]);
  if (!active || !auth.isAdmin || catalog.value?.version !== value.version) return;
  status.value = effective;
  versions.value = newVersions;
  audit.value = newAudit;
}
async function act(action: () => Promise<void>) {
  if (busy.value || !auth.isAdmin) return;
  busy.value = true; error.value = ""; notice.value = "";
  try { await action(); }
  catch (failure) {
    if (active) {
      error.value = systemModelError(failure);
      if ((failure as { response?: { status?: number } })?.response?.status === 403 && auth.user) auth.user.role = "USER";
    }
  }
  finally { busy.value = false; }
}
async function refresh() {
  clearSecret();
  await act(async () => {
    const [value, limits] = await Promise.all([systemModels.catalog(), systemModels.policy()]);
    if (!active || !auth.isAdmin) return;
    policy.value = limits;
    await applyCatalog(value);
    editProvider(); editModel();
  });
  loading.value = false;
}
async function saveProvider() {
  const data = { expectedVersion: catalog.value!.version, name: provider.name, protocol: provider.protocol,
    baseUrl: provider.baseUrl, enabled: provider.enabled, clearKey: provider.clearKey,
    ...(provider.apiKey ? { apiKey: provider.apiKey } : {}) };
  clearSecret();
  await act(async () => {
    try {
      const before = new Set(catalog.value!.providers.map(p => p.id));
      const value = await systemModels.saveProvider(selectedProvider.value ? Number(selectedProvider.value) : null, data);
      await applyCatalog(value);
      if (!active) return;
      if (!selectedProvider.value) selectedProvider.value = String(value.providers.find(p => !before.has(p.id))?.id ?? "");
      editProvider(); notice.value = "供应商已保存，新任务使用新版本。";
    } finally { delete data.apiKey; clearSecret(); }
  });
}
async function saveModel() {
  await act(async () => {
    const before = new Set(catalog.value!.models.map(m => m.id));
    const parameters = Object.fromEntries(["temperature", "maxTokens", "timeoutMillis", "maxAttempts"].map(key => [key,
      String(model[key as "temperature"]).trim() === "" ? null : Number(model[key as "temperature"])]));
    const value = await systemModels.saveModel(selectedModel.value ? Number(selectedModel.value) : null, Number(model.providerId), {
      expectedVersion: catalog.value!.version, model: model.model, capabilities: [...model.capabilities], parameters, enabled: model.enabled,
    });
    await applyCatalog(value);
    if (!active) return;
    if (!selectedModel.value) selectedModel.value = String(value.models.find(m => !before.has(m.id))?.id ?? "");
    editModel(); notice.value = "模型已保存；声明能力仍需供应商实际支持。";
  });
}
async function saveBindings() {
  await act(async () => {
    const changes = Object.fromEntries(connectedFeatures.value.filter(f => bindingDraft[f.key] !== String(catalog.value!.bindings[f.key] ?? ""))
      .map(f => [f.key, bindingDraft[f.key] ? Number(bindingDraft[f.key]) : null]));
    await applyCatalog(await systemModels.bindings(catalog.value!.version, changes));
    notice.value = "绑定已保存，新任务使用新版本；执行中的任务继续原快照。";
  });
}
async function probe(id: number) {
  await act(async () => {
    const version = catalog.value!.version;
    const result = await systemModels.probe(version, id);
    if (!active || catalog.value?.version !== version) return;
    if (result.version !== version || result.modelId !== id) throw new Error("Invalid result identity");
    probes.value = { ...probes.value, [id]: result };
  });
}
async function readHistory() {
  await act(async () => { const value = await systemModels.version(Number(selectedHistory.value)); if (active) history.value = value; });
}
async function rollback() {
  await act(async () => {
    await applyCatalog(await systemModels.rollback(catalog.value!.version, rollbackFeature.value, Number(selectedHistory.value)));
    notice.value = "已恢复指定功能的历史绑定，并生成新版本。";
  });
}
async function deleteProvider() {
  clearSecret();
  await act(async () => {
    await applyCatalog(await systemModels.deleteProvider(Number(selectedProvider.value), catalog.value!.version));
    selectedProvider.value = ""; editProvider();
  });
}
async function deleteModel() {
  await act(async () => {
    await applyCatalog(await systemModels.deleteModel(Number(selectedModel.value), catalog.value!.version));
    selectedModel.value = ""; editModel();
  });
}
async function findExecutions() {
  await act(async () => { const value = await systemModels.executions(taskId.value.trim()); if (active) executions.value = value; });
}
watch(() => auth.isAdmin, admin => { if (!admin) { clearSecret(); catalog.value = undefined; status.value = undefined; history.value = undefined; executions.value = []; } });
onMounted(() => {
  window.addEventListener("pagehide", clearSecret);
  if (auth.isAdmin) void refresh(); else loading.value = false;
});
onBeforeUnmount(() => { active = false; clearSecret(); window.removeEventListener("pagehide", clearSecret); });
</script>

<template>
  <main class="admin-models page-container">
    <PageHeading eyebrow="管理员设置" title="系统模型" description="为课程处理、问答和视觉分析配置模型。每次保存生成新版本，新任务使用新配置，执行中的任务继续原快照。">
      <template #actions><RouterLink to="/settings/models">个人学习 Agent 模型 →</RouterLink></template>
    </PageHeading>
    <p v-if="!auth.isAdmin" role="alert">需要管理员权限。</p>
    <template v-else>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <p v-if="notice" role="status" class="notice">{{ notice }}</p>
      <div class="toolbar"><span v-if="catalog" data-testid="config-version">当前配置版本 {{ catalog.version }}</span><button type="button" :disabled="busy" @click="refresh">刷新配置</button></div>
      <p v-if="loading">正在读取系统配置…</p>
      <template v-if="catalog">
        <SectionPanel title="功能绑定与有效配置" :description="`当前字幕翻译模式：${catalog.fullTextTranslation ? '全文翻译' : '逐段翻译'}。配置可解析只代表本地检查通过，连通性需手动测试。`">
          <div class="table-scroll"><table aria-label="功能有效配置"><thead><tr><th>功能 / 状态</th><th>实际来源 / 版本</th><th>模型 / 密钥</th><th>最终请求地址</th><th>新绑定</th></tr></thead><tbody>
            <tr v-for="feature in status?.features" :key="feature.key" :data-feature="feature.key">
              <th scope="row">{{ featureNames[feature.key] ?? feature.key }}<small><StatusBadge :label="configurationNames[feature.configurationStatus] ?? '未检查'" :tone="feature.configurationStatus === 'READY' ? 'neutral' : feature.configurationStatus === 'MOCK' ? 'warning' : 'danger'" /><template v-if="feature.connected && !feature.active"> · 当前模式或部署开关未启用</template></small></th>
              <td>{{ sourceNames[feature.source] ?? feature.source }}<small>版本 {{ feature.version }}</small></td>
              <td>{{ catalog.effective[feature.key]?.model ?? '—' }}<small>{{ maskedKey(catalog.effective[feature.key]) }}</small></td>
              <td class="endpoint">{{ feature.finalUrl ?? '—' }}</td>
              <td><select v-if="feature.connected" v-model="bindingDraft[feature.key]" :aria-label="`${featureNames[feature.key]}绑定`" :disabled="busy"><option value="">部署默认</option><option v-for="candidate in candidates(feature.key)" :key="candidate.id" :value="String(candidate.id)">{{ providerName(candidate.providerId) }} / {{ candidate.model }}</option></select><span v-else>未接通</span></td>
            </tr>
          </tbody></table></div>
          <button type="button" :disabled="busy || !bindingChanged" @click="saveBindings">保存功能绑定</button>
        </SectionPanel>

        <div class="editors">
          <SectionPanel title="供应商" description="更改地址或协议时需重新输入密钥或明确清除。已绑定的供应商不能停用或清除密钥。">
            <label>编辑供应商<select v-model="selectedProvider" aria-label="编辑供应商" :disabled="busy"><option value="">新增供应商</option><option v-for="p in catalog.providers" :key="p.id" :value="String(p.id)">{{ p.name }} · {{ maskedKey(p) }}</option></select></label>
            <form aria-label="供应商设置" @submit.prevent="saveProvider"><fieldset :disabled="busy">
              <label>名称<input v-model="provider.name" required maxlength="80" /></label>
              <label>协议<select v-model="provider.protocol"><option>OPENAI_CHAT</option><option>BAILIAN_ASR</option><option>SILICONFLOW_ASR</option></select></label>
              <label>服务地址<input v-model="provider.baseUrl" required type="url" maxlength="1900" placeholder="https://api.deepseek.com" /></label>
              <small>Chat 地址保留前缀，不自动加 /v1；百炼 ASR 填完整同步端点，SiliconFlow 使用 origin 下的 /v1/audio/transcriptions。</small>
              <label>API Key · {{ maskedKey(providerRecord) }}<input v-model="provider.apiKey" type="password" autocomplete="new-password" maxlength="4096" :placeholder="providerRecord?.hasKey ? '留空保留已保存密钥' : '输入密钥'" /></label>
              <div class="checks"><label><input v-model="provider.clearKey" type="checkbox" :disabled="Boolean(provider.apiKey)" />清除密钥</label><label><input v-model="provider.enabled" type="checkbox" />启用供应商</label></div>
              <div class="actions"><button type="submit">保存供应商</button><button v-if="selectedProvider" type="button" :disabled="catalog.models.some(m => m.providerId === Number(selectedProvider))" @click="deleteProvider">删除供应商</button></div>
            </fieldset></form>
          </SectionPanel>
          <SectionPanel title="模型" description="填写供应商提供的精确模型 ID。能力声明用于限制绑定，不代表已验证支持。">
            <label>编辑模型<select v-model="selectedModel" aria-label="编辑模型" :disabled="busy"><option value="">新增模型</option><option v-for="m in catalog.models" :key="m.id" :value="String(m.id)">{{ providerName(m.providerId) }} / {{ m.model }}</option></select></label>
            <form aria-label="模型设置" @submit.prevent="saveModel"><fieldset :disabled="busy">
              <label>所属供应商<select v-model="model.providerId" required :disabled="Boolean(selectedModel)"><option value="" disabled>选择供应商</option><option v-for="p in catalog.providers" :key="p.id" :value="String(p.id)">{{ p.name }}</option></select></label>
              <label>模型 ID<input v-model="model.model" required maxlength="128" /></label>
              <div class="capabilities" aria-label="模型能力声明"><ModelPickerOption v-for="cap in capabilities" :key="cap.key" :model="cap.key" :guide="{ category: 'unknown', label: '能力声明', description: cap.description }" :checked="model.capabilities.includes(cap.key)" :disabled="busy" status="需供应商支持" @toggle="toggleCapability" /></div>
              <div class="parameters"><label>温度<input v-model="model.temperature" type="number" min="0" max="2" step="0.1" placeholder="默认" /></label><label>输出 token 上限<input v-model="model.maxTokens" type="number" min="1" max="32768" placeholder="默认" /></label><label>超时（毫秒）<input v-model="model.timeoutMillis" type="number" min="100" max="180000" placeholder="默认" /></label><label>最多尝试次数<input v-model="model.maxAttempts" type="number" min="1" max="3" placeholder="默认" /></label></div>
              <label class="check"><input v-model="model.enabled" type="checkbox" />启用模型</label>
              <div class="actions"><button type="submit" :disabled="!model.providerId">保存模型</button><button v-if="selectedModel" type="button" :disabled="Object.values(catalog.bindings).includes(Number(selectedModel))" @click="deleteModel">删除模型</button></div>
            </fieldset></form>
          </SectionPanel>
        </div>

        <SectionPanel title="手动连通性测试" description="仅测试已保存的供应商和模型，每次点击发送一次小请求。JSON 测试不验证工具调用或视觉能力；ASR 使用仓库授权的一秒合成音频，不验证识别质量。">
          <p v-if="policy" class="policy">限时 {{ policy.timeoutMillis / 1000 }} 秒 · 单实例最多 {{ policy.concurrency }} 个并发 · 响应最多 {{ policy.responseLimitBytes / 1024 }} KiB。<template v-if="!policy.allowedOrigins.length">部署管理员尚未开放测试地址白名单。</template></p>
          <details v-if="policy?.allowedOrigins.length"><summary>测试地址白名单</summary><p v-for="origin in policy.allowedOrigins" :key="origin">{{ origin }}</p></details>
          <ul class="probe-list"><li v-for="m in catalog.models" :key="m.id" :data-model="m.id"><div><strong>{{ providerName(m.providerId) }} / {{ m.model }}</strong><p v-if="probes[m.id]">{{ probeNames[probes[m.id]!.category] ?? '测试失败' }} · {{ probes[m.id]!.elapsedMillis }} 毫秒 · 版本 {{ probes[m.id]!.version }}</p><p v-else>当前版本尚未测试</p><small class="endpoint" v-if="probes[m.id]?.finalUrl">{{ probes[m.id]!.finalUrl }}</small></div><button type="button" :disabled="busy || !m.enabled || !catalog.providers.find(p => p.id === m.providerId)?.enabled || !policy?.allowedOrigins.length" @click="probe(m.id)">{{ catalog.providers.find(p => p.id === m.providerId)?.protocol === 'OPENAI_CHAT' ? '测试 JSON 连接' : '测试 ASR 连接' }}</button></li></ul>
          <p v-if="!catalog.models.length">保存供应商和模型后，可手动测试连接。</p>
        </SectionPanel>

        <SectionPanel title="历史版本与恢复绑定" description="最近 50 个版本。恢复只改变所选功能的绑定，并生成新版本；不会恢复已删除的供应商或模型，也不会还原它们的字段。">
          <div class="actions"><select v-model="selectedHistory" aria-label="历史版本" :disabled="busy"><option value="">选择历史版本</option><option v-for="v in versions" :key="v.version" :value="String(v.version)">版本 {{ v.version }} · {{ v.reason }}</option></select><button type="button" :disabled="busy || !selectedHistory" @click="readHistory">查看历史配置</button></div>
          <div v-if="history" data-testid="history"><h3>历史版本 {{ history.version }}</h3><ul><li v-for="p in history.config.providers" :key="p.id">{{ p.name }} · {{ p.protocol }} · {{ maskedKey(p) }}</li></ul><ul><li v-for="(route, key) in history.config.effective" :key="key">{{ featureNames[key] ?? key }} · {{ sourceNames[route.source] ?? route.source }} · {{ route.model ?? '—' }} · {{ maskedKey(route) }}</li></ul></div>
          <div class="actions"><select v-model="rollbackFeature" aria-label="恢复的功能" :disabled="busy"><option v-for="f in connectedFeatures" :key="f.key" :value="f.key">{{ featureNames[f.key] }}</option></select><button type="button" :disabled="busy || !selectedHistory" @click="rollback">恢复该功能到所选版本的绑定</button></div>
        </SectionPanel>
        <SectionPanel title="任务执行快照" description="按课程任务 ID 查询最近 50 条快照。恢复或重试沿用原快照。">
          <form class="actions" aria-label="查询执行快照" @submit.prevent="findExecutions"><input v-model="taskId" aria-label="任务 ID" required maxlength="64" placeholder="课程任务 ID" /><button type="submit" :disabled="busy">查询快照</button></form>
          <ul><li v-for="execution in executions" :key="execution.id">{{ execution.operationType }} · 版本 {{ execution.configVersion }} · {{ execution.origin }}<small>{{ execution.id }}</small><ul><li v-for="(route, key) in execution.routes" :key="key">{{ featureNames[key] ?? key }} · {{ sourceNames[route.source] ?? route.source }} · {{ route.model ?? '—' }} · {{ maskedKey(route) }}</li></ul></li></ul>
        </SectionPanel>
        <SectionPanel title="变更审计" description="最近 50 条配置变更。"><ul><li v-for="entry in audit" :key="entry.id">{{ entry.createdAt }} · {{ entry.action }} · {{ entry.objectType }}/{{ entry.objectId }} · 版本 {{ entry.version ?? '—' }}</li></ul></SectionPanel>
      </template>
    </template>
  </main>
</template>

<style scoped>
.admin-models{max-width:1280px;margin:0 auto;padding:32px 24px 64px;display:grid;gap:24px}.toolbar,.actions,.checks{display:flex;align-items:center;flex-wrap:wrap;gap:12px}.toolbar{justify-content:space-between}.editors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}form,fieldset{display:grid;gap:14px}fieldset{border:0;margin:16px 0 0;padding:0;min-width:0}label{display:grid;gap:7px;font-size:13px;font-weight:600}input,select{width:100%;min-width:0;min-height:38px;padding:8px 10px;border:1px solid var(--color-border);border-radius:6px;background:var(--color-surface);color:var(--color-ink);font:inherit}input[type=checkbox]{width:16px;min-height:16px;padding:0;margin:0}.checks label,.check{display:flex;align-items:center;gap:6px}button{padding:9px 14px;min-height:38px;border:1px solid var(--color-border);border-radius:6px;background:var(--color-brand-soft);color:var(--color-brand-strong);font:inherit;cursor:pointer}button:disabled{opacity:.5;cursor:default}small{display:block;margin-top:6px;color:var(--color-ink-muted);font-weight:400;font-size:12px;line-height:1.5}.error{color:var(--color-danger)}.notice{color:var(--color-success)}.parameters{display:grid;grid-template-columns:1fr 1fr;gap:12px}.admin-models>*{min-width:0}.editors>*{min-width:0}.table-scroll{overflow:auto;min-width:0;max-width:100%;margin-bottom:16px}table{border-collapse:collapse;width:100%;min-width:1000px;font-size:13px}td,th{padding:12px 10px;text-align:left;border-bottom:1px solid var(--color-border);vertical-align:top}td select{min-width:180px}.endpoint{overflow-wrap:anywhere;word-break:break-word;max-width:360px}.probe-list{padding:0;list-style:none}.probe-list>li{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--color-border);padding:14px 0}.probe-list p,.policy{font-size:13px;color:var(--color-ink-muted)}.actions select,.actions input{width:auto;flex:1}li{margin-bottom:8px;font-size:13px;line-height:1.6}summary{cursor:pointer;color:var(--color-brand-strong)}a{color:var(--color-brand-strong)}@media(max-width:800px){.editors{grid-template-columns:1fr}.admin-models{padding:24px 16px}.probe-list>li{align-items:flex-start;flex-direction:column}.actions{align-items:stretch;flex-direction:column}.actions select,.actions input{width:100%}}
</style>
