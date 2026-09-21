<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElOption, ElOptionGroup, ElSelect } from "element-plus";
import ModelPickerOption from "../components/ModelPickerOption.vue";
import { modelGuide, groupModelVersions } from "../lib/modelDiscovery";
import PageHeading from "../components/ui/PageHeading.vue";
import { modelCommand, modelError, type ModelBinding, type ModelCatalog, type ModelConnection, type ModelDiscovery } from "../api/models";

const catalog = ref<ModelCatalog | null>(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const selectedId = ref("");
const decision = ref("environment");
const review = ref("environment");
const presets = computed(() => catalog.value?.presets ?? []);
const preset = ref("");
const presetSearch = ref("");
const form = reactive({ name: "", base_url: "", api_key: "", clear_key: false, models: "", enabled: true });
const activePreset = computed(() => presets.value.find(item => item.base_url === form.base_url.trim().replace(/\/+$/, "")));
const presetGroups = computed(() => {
  const query = presetSearch.value.trim().toLowerCase();
  const matching = presets.value.filter(item => item.id === preset.value || [item.name, item.group, item.base_url, ...item.models].join(" ").toLowerCase().includes(query));
  return [...new Set(matching.map(item => item.group))].map(name => ({ name, items: matching.filter(item => item.group === name) }));
});
const selected = computed(() => catalog.value?.connections.find(item => item.connection_id === selectedId.value));
const modelSearch = ref("");
const modelPage = ref(1);
const modelPageSize = 6;
const matchingModels = computed(() => (selected.value?.model_ids ?? []).filter(model => model.toLowerCase().includes(modelSearch.value.trim().toLowerCase())));
const modelPageCount = computed(() => Math.max(1, Math.ceil(matchingModels.value.length / modelPageSize)));
const currentModelPage = computed(() => Math.min(modelPage.value, modelPageCount.value));
const visibleModels = computed(() => matchingModels.value.slice((currentModelPage.value - 1) * modelPageSize, currentModelPage.value * modelPageSize));
watch(selectedId, () => { modelSearch.value = ""; modelPage.value = 1; });
watch(modelSearch, () => { modelPage.value = 1; });
const modelIds = computed(() => [...new Set(form.models.split(/\r?\n/).map(s => s.trim()).filter(Boolean))]);
const connectionDirty = computed(() => !selected.value || form.name !== selected.value.name || form.base_url !== selected.value.base_url || form.enabled !== selected.value.enabled || Boolean(form.api_key) || form.clear_key);
const dirty = computed(() => connectionDirty.value || JSON.stringify(modelIds.value) !== JSON.stringify(selected.value?.model_ids));
const boundModels = computed(() => Object.values(catalog.value?.bindings ?? {}).filter(binding => binding.connection_id === selectedId.value && binding.model).map(binding => binding.model!));
const pickerMode = ref<"add" | "manage" | null>(null);
const pickerModels = ref<string[]>([]);
const pickerSelection = ref<string[]>([]);
const pickerSearch = ref("");
const pickerSearchInput = ref<HTMLInputElement>();
const pickerList = ref<HTMLDivElement>();
const pickerFilter = ref<"candidate" | "all" | "other">("candidate");
const discoveryInfo = ref<ModelDiscovery>();
const isBailian = computed(() => activePreset.value?.id.startsWith("bailian") ?? false);
const pickerGuides = computed(() => Object.fromEntries(pickerModels.value.map(id => [id, modelGuide(id, isBailian.value)])));
const otherCount = computed(() => pickerModels.value.filter(id => pickerGuides.value[id]?.category === "other").length);
const pickerMatches = computed(() => pickerModels.value.filter(model => {
  const guide = pickerGuides.value[model]!;
  const inScope = pickerFilter.value === "all" || (pickerFilter.value === "other" ? guide.category === "other" : guide.category !== "other");
  return inScope && `${model} ${guide.label} ${guide.description}`.toLowerCase().includes(pickerSearch.value.trim().toLowerCase());
}).sort((a, b) => {
  const rank = { candidate: 0, unknown: 1, other: 2 };
  return rank[pickerGuides.value[a]!.category] - rank[pickerGuides.value[b]!.category];
}));
const pickerGroups = computed(() => groupModelVersions(pickerMatches.value, Boolean(pickerSearch.value.trim()) || pickerMode.value === "manage"));
watch([pickerSearch, pickerFilter], () => { if (pickerList.value) pickerList.value.scrollTop = 0; }, { flush: "post" });
const options = computed(() => catalog.value?.connections.filter(c => c.enabled).flatMap(c => c.model_ids.map(model => ({ value: JSON.stringify([c.connection_id, model]), label: `${c.name} · ${model}` }))) ?? []);
const modelGroups = computed(() => catalog.value?.connections.filter(c => c.enabled && c.model_ids.length) ?? []);
let alive = true;
onBeforeUnmount(() => { alive = false; form.api_key = ""; });

function encode(binding: ModelBinding) { return binding.connection_id ? JSON.stringify([binding.connection_id, binding.model]) : "environment"; }
function decode(value: string): ModelBinding { if (value === "environment") return {}; const [connection_id, model] = JSON.parse(value) as [string, string]; return { connection_id, model }; }
function edit(connection?: ModelConnection) {
  pickerMode.value = null;
  selectedId.value = connection?.connection_id ?? "";
  Object.assign(form, { name: connection?.name ?? "", base_url: connection?.base_url ?? "", api_key: "", clear_key: false, models: connection?.model_ids.join("\n") ?? "", enabled: connection?.enabled ?? true });
  preset.value = activePreset.value?.id ?? "";
  presetSearch.value = "";
}
async function openPicker(mode: "add" | "manage", models: string[]) {
  pickerMode.value = mode;
  pickerModels.value = [...new Set(models)];
  pickerSelection.value = mode === "manage" ? [...modelIds.value] : [];
  pickerSearch.value = "";
  pickerFilter.value = mode === "add" ? "candidate" : "all";
  await nextTick();
  if (pickerList.value) pickerList.value.scrollTop = 0;
  pickerSearchInput.value?.focus();
}
function pickerLocked(model: string) {
  return pickerMode.value === "add" ? modelIds.value.includes(model) : boundModels.value.includes(model);
}
function pickerStatus(model: string) {
  const check = selected.value?.checks[model];
  const status = check && check.version === selected.value?.version ? (check.ok ? "单次工具测试通过" : "工具测试未通过") : "本项目未测试";
  return pickerLocked(model) ? `${pickerMode.value === "add" ? "已添加" : "正在使用"} · ${status}` : status;
}
function togglePickerModel(model: string) {
  if (pickerLocked(model)) return;
  pickerSelection.value = pickerSelection.value.includes(model) ? pickerSelection.value.filter(id => id !== model) : [...pickerSelection.value, model];
}
function applyPicker() {
  if (pickerMode.value === "add") {
    const combined = [...new Set([...modelIds.value, ...pickerSelection.value])];
    if (combined.length > 80) return;
    form.models = combined.join("\n");
  } else {
    form.models = pickerModels.value.filter(model => pickerSelection.value.includes(model) || boundModels.value.includes(model)).join("\n");
  }
  pickerMode.value = null;
  notice.value = `已选择 ${modelIds.value.length} 个模型，请保存连接后使用。`;
}
function applyPreset() {
  const item = presets.value.find(item => item.id === preset.value);
  if (!item) return;
  // A different service starts a new connection draft, never repurposes a saved credential.
  edit();
  preset.value = item.id;
  form.name = item.name;
  form.base_url = item.base_url;
  notice.value = "已填入服务地址。添加模型并保存连接后，再测试可用性。";
}
function addModel(model: string) {
  if (!modelIds.value.includes(model) && modelIds.value.length < 80) {
    form.models = [...modelIds.value, model].join("\n");
  }
}
async function load(selectFirst = false) {
  const result = await modelCommand({ operation: "LIST" });
  if (!alive) return;
  catalog.value = result;
  decision.value = encode(result.bindings.decision); review.value = encode(result.bindings.review);
  const current = result.connections.find(c => c.connection_id === selectedId.value);
  if (current) edit(current); else if (selectFirst) edit(result.connections[0]);
}
async function action(work: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  try { await work(); } catch (failure) { if (alive) error.value = modelError(failure); }
  finally { if (alive) busy.value = false; }
}
onMounted(async () => { await action(() => load(true)); if (alive) loading.value = false; });
async function save() {
  if (boundModels.value.some(model => !modelIds.value.includes(model))) {
    error.value = "请先更换正在使用的决策或复核模型并保存用途，再移除该模型。";
    return;
  }
  await action(async () => {
    const result = await modelCommand<{ connection_id: string }>({ operation: "SAVE", ...(selected.value ? { connection_id: selectedId.value, version: selected.value.version } : {}), connection: { name: form.name.trim(), base_url: form.base_url.trim(), enabled: form.enabled, model_ids: modelIds.value, clear_key: form.clear_key, ...(form.api_key ? { api_key: form.api_key } : {}) } });
    if (!alive) return;
    form.api_key = ""; selectedId.value = result.connection_id;
    await load(); notice.value = "连接已保存。可获取模型列表，或测试已填写的模型。";
  });
}
async function discover() {
  if (!selected.value) return;
  const connection = selected.value;
  await action(async () => {
    const result = await modelCommand<ModelDiscovery>({ operation: "DISCOVER", connection_id: connection.connection_id, version: connection.version });
    if (!alive) return;
    discoveryInfo.value = result;
    await openPicker("add", result.model_ids);
    notice.value = `获取到 ${result.model_ids.length} 个模型；默认展示课程 Agent 候选，请按需勾选。`;
  });
  await nextTick();
  if (alive && pickerMode.value === "add") pickerSearchInput.value?.focus();
}
async function probe(model: string) {
  if (!selected.value) return;
  const connection = selected.value;
  await action(async () => {
    const result = await modelCommand<{ check: { ok: boolean; latency_ms: number } }>({ operation: "PROBE", connection_id: connection.connection_id, version: connection.version, model });
    if (!alive) return;
    await load(); notice.value = result.check.ok ? `工具调用测试通过，用时 ${result.check.latency_ms} ms。` : "测试未通过，请检查连接配置和模型工具调用支持。";
  });
}
async function saveRoutes() {
  await action(async () => { await modelCommand({ operation: "ROUTE", bindings: { decision: decode(decision.value), review: decode(review.value) } }); if (alive) notice.value = "模型用途已保存，将用于新创建的 Agent 运行。"; });
}
async function clearRoutes() {
  await action(async () => { await modelCommand({ operation: "CLEAR_ROUTES" }); if (!alive) return; await load(); notice.value = "用途选择已清除。新运行会使用服务器默认模型；未配置默认模型时，需要重新选择。"; });
}
async function remove() {
  if (!selected.value) return;
  const connection = selected.value;
  await action(async () => { await modelCommand({ operation: "DELETE", connection_id: connection.connection_id, version: connection.version }); if (!alive) return; edit(); await load(true); notice.value = "连接已删除。"; });
}
</script>

<template>
  <main class="model-page">
    <PageHeading title="模型管理" description="连接你的模型服务，为 Agent 的不同任务选择合适的模型。配置仅对你的账号生效。" />
    <p v-if="loading" role="status">正在读取模型配置…</p>
    <p v-if="error" class="feedback error" role="alert">{{ error }} <button type="button" :disabled="busy" @click="action(() => load(true))">刷新配置</button></p>
    <p v-if="notice" class="feedback" role="status">{{ notice }}</p>
    <template v-if="catalog">
      <section class="routing panel" aria-labelledby="routing-title">
        <div><span class="eyebrow">AGENT MODELS</span><h2 id="routing-title">按任务选择模型</h2><p>新运行会保存所选模型与连接版本。修改、停用或删除连接后，已有运行仍沿用原配置。</p></div>
        <p v-if="catalog.environment.mode === 'mock'" class="feedback">当前学习助手为固定模型演示模式，下面的配置会在启用真实模型模式后使用。</p>
        <div class="route-fields">
          <label>Agent 决策<ElSelect v-model="decision" filterable fit-input-width :disabled="busy" aria-label="Agent 决策模型" placeholder="搜索并选择决策模型" no-match-text="没有匹配的模型" no-data-text="请先保存模型连接" popper-class="model-route-dropdown"><ElOption value="environment" :disabled="!catalog.environment.available" :label="catalog.environment.available ? `服务器默认 · ${catalog.environment.model}` : '请选择模型（服务器默认未配置）'" /><ElOptionGroup v-for="connection in modelGroups" :key="connection.connection_id" :label="connection.name"><ElOption v-for="model in connection.model_ids" :key="model" :value="JSON.stringify([connection.connection_id, model])" :label="`${connection.name} · ${model}`" /></ElOptionGroup></ElSelect><small>理解目标、选择工具、解释与出题；支持输入模型名搜索</small></label>
          <label>草稿复核<ElSelect v-model="review" filterable fit-input-width :disabled="busy" aria-label="草稿复核模型" placeholder="搜索并选择复核模型" no-match-text="没有匹配的模型" no-data-text="请先保存模型连接" popper-class="model-route-dropdown"><ElOption value="environment" :disabled="!catalog.environment.available" :label="catalog.environment.available ? `服务器默认 · ${catalog.environment.model}` : '请选择模型（服务器默认未配置）'" /><ElOptionGroup v-for="connection in modelGroups" :key="connection.connection_id" :label="connection.name"><ElOption v-for="model in connection.model_ids" :key="model" :value="JSON.stringify([connection.connection_id, model])" :label="`${connection.name} · ${model}`" /></ElOptionGroup></ElSelect><small>检查答案、引用和题型；支持输入模型名搜索</small></label>
        </div>
        <div class="actions"><button class="primary" :disabled="busy || !options.length && !catalog.environment.available" @click="saveRoutes">保存模型用途</button><button :disabled="busy" @click="clearRoutes">清除用途选择</button></div>
      </section>
      <div class="connection-layout">
        <aside class="panel connection-list" aria-label="我的模型连接">
          <div class="section-heading"><h2>我的连接 <span>{{ catalog.connections.length }}</span></h2><button :disabled="busy" @click="edit()">＋ 新建</button></div>
          <p v-if="!catalog.connections.length" class="muted">添加云端 API 或服务端本机的模型服务。</p>
          <button v-for="connection in catalog.connections" :key="connection.connection_id" class="connection-card" :class="{ selected: selectedId === connection.connection_id }" :disabled="busy" :aria-pressed="selectedId === connection.connection_id" @click="edit(connection)"><strong>{{ connection.name }}</strong><span>{{ connection.model_ids.length }} 个模型 · {{ connection.enabled ? '已启用' : '已停用' }}</span><small>{{ connection.base_url }}</small></button>
        </aside>
        <section class="panel editor" aria-labelledby="connection-title">
          <div class="section-heading"><h2 id="connection-title">{{ selected ? '编辑连接' : '新建连接' }}</h2><span class="protocol">Chat Completions 兼容接口</span></div>
          <form @submit.prevent="save">
            <fieldset :disabled="busy">
              <div class="preset-fields">
                <label>搜索服务或模型<input v-model="presetSearch" type="search" placeholder="百炼、Kimi、GLM、GPT…" /></label>
                <label>服务预设<select v-model="preset" aria-label="服务预设" @change="applyPreset"><option value="">自定义兼容服务</option><optgroup v-for="group in presetGroups" :key="group.name" :label="group.name"><option v-for="item in group.items" :key="item.id" :value="item.id">{{ item.name }}</option></optgroup></select></label>
              </div>
              <p v-if="presetSearch && !presetGroups.length" class="muted">没有匹配的服务，可填写自定义兼容服务。</p>
              <p v-if="activePreset" class="preset-note">{{ activePreset.note }} <a :href="activePreset.docs_url" target="_blank" rel="noopener noreferrer">官方接入说明 ↗</a></p>
              <div class="form-pair"><label>连接名称<input v-model="form.name" required maxlength="80" placeholder="例如：我的 DeepSeek" /></label><label>服务基础地址<input v-model="form.base_url" required type="url" maxlength="500" placeholder="https://api.example.com/v1" /></label></div>
              <label>API Key<input v-model="form.api_key" type="password" autocomplete="new-password" maxlength="4096" :placeholder="selected?.has_key ? '已保存密钥，留空表示不修改' : '本地无鉴权服务可留空'" /></label>
              <div class="check-row"><label><input v-model="form.clear_key" type="checkbox" :disabled="Boolean(form.api_key)" />清除已保存的密钥</label><label><input v-model="form.enabled" type="checkbox" />启用此连接</label></div>
              <label>模型 ID（每行一个）<textarea v-model="form.models" rows="4" placeholder="填入服务商提供的模型 ID，也可先保存连接，再获取模型列表。" /></label>
              <div class="model-selection-summary"><span>已添加 {{ modelIds.length }} / 80 个模型</span><button type="button" :disabled="!modelIds.length" @click="openPicker('manage', modelIds)">整理已添加模型</button></div>
              <section v-if="pickerMode" class="model-picker" aria-label="模型选取">
                <h3>{{ pickerMode === 'add' ? '选择要添加的模型' : '选择要保留的模型' }}</h3>
                <p>{{ pickerMode === 'add' ? '只添加你勾选的模型，已有模型保持不变。' : '取消勾选可移除模型；正在用于决策或复核的模型会保留。' }}完成选择后，保存连接才会生效。</p>
                <div class="picker-filters" role="group" aria-label="按模型用途筛选">
                  <button type="button" :aria-pressed="pickerFilter === 'candidate'" @click="pickerFilter = 'candidate'">课程 Agent 候选（{{ pickerModels.length - otherCount }}）</button>
                  <button type="button" :aria-pressed="pickerFilter === 'all'" @click="pickerFilter = 'all'">全部（{{ pickerModels.length }}）</button>
                  <button type="button" :aria-pressed="pickerFilter === 'other'" @click="pickerFilter = 'other'">其他用途（{{ otherCount }}）</button>
                </div>
                <p class="picker-guide">候选包含用途待识别型号，不代表兼容性已验证。搜索可展开日期版本；官方能力与本项目测试分开标注。</p>
                <p v-if="pickerMode === 'add' && (discoveryInfo?.truncated || discoveryInfo?.provider_has_more)" class="picker-warning" role="status">目录未完整展示：本次返回 {{ discoveryInfo.total_count ?? pickerModels.length }} 个有效型号，展示 {{ pickerModels.length }} 个<span v-if="discoveryInfo.provider_has_more">；服务商还有后续页</span>。未显示的模型可手动填写 ID。</p>
                <p v-if="pickerMode === 'add' && discoveryInfo?.skipped_count" class="picker-guide">已跳过 {{ discoveryInfo.skipped_count }} 项无效型号。</p>
                <input ref="pickerSearchInput" v-model="pickerSearch" type="search" aria-label="搜索待选模型" placeholder="搜索名称或用途，如 qwen、翻译" />
                <div class="picker-selection-count"><span aria-live="polite">共 {{ pickerMatches.length }} 项 · 已勾选 {{ pickerSelection.length }} 个</span><button type="button" @click="pickerSelection = pickerMode === 'manage' ? pickerModels.filter(model => boundModels.includes(model)) : []">清空选择</button></div>
                <div v-if="pickerMatches.length" ref="pickerList" class="model-picker-list" role="region" aria-label="可滚动的待选模型列表" tabindex="0">
                  <div v-for="group in pickerGroups" :key="group.id" class="picker-family">
                    <template v-for="model in [group.id]" :key="model"><ModelPickerOption :model="model" :guide="pickerGuides[model]!" :checked="pickerSelection.includes(model) || pickerLocked(model)" :disabled="pickerLocked(model) || (pickerMode === 'add' && !pickerSelection.includes(model) && modelIds.length + pickerSelection.length >= 80)" :status="pickerStatus(model)" @toggle="togglePickerModel" /></template>
                    <details v-if="group.versions.length" class="picker-versions">
                      <summary>其他日期版本（{{ group.versions.length }}）<span v-if="group.versions.some(id => pickerSelection.includes(id))"> · 含已勾选</span></summary>
                      <template v-for="model in group.versions" :key="model"><ModelPickerOption :model="model" :guide="pickerGuides[model]!" :checked="pickerSelection.includes(model) || pickerLocked(model)" :disabled="pickerLocked(model) || (pickerMode === 'add' && !pickerSelection.includes(model) && modelIds.length + pickerSelection.length >= 80)" :status="pickerStatus(model)" @toggle="togglePickerModel" /></template>
                    </details>
                  </div>
                </div>
                <p v-if="!pickerMatches.length" role="status">当前分类没有匹配的模型，可切换“全部”、修改搜索或手动填写模型 ID。</p>
                <div class="picker-actions"><button type="button" @click="pickerMode = null">取消</button><button class="primary" type="button" :disabled="pickerMode === 'add' && !pickerSelection.length" @click="applyPicker">{{ pickerMode === 'add' ? '添加所选' : '保留所选' }}（{{ pickerSelection.length }}）</button></div>
              </section>
              <div v-if="activePreset?.models.length" class="model-suggestions" aria-label="常用模型快捷添加">
                <span>常用模型</span><button v-for="model in activePreset.models" :key="model" type="button" :disabled="modelIds.includes(model) || modelIds.length >= 80" @click="addModel(model)">{{ modelIds.includes(model) ? '已添加 · ' : '＋ ' }}{{ model }}</button>
              </div>
              <p class="muted">预设与常用模型仅供快速填写，不代表账号已开通或通过测试。可手动添加其他模型；获取列表失败时可从服务商控制台复制 ID。</p>
              <p class="muted">密钥加密保存在服务端，不会回显。首次保存无需填写模型 ID。localhost 指 Agent 服务所在机器。</p>
              <div class="actions"><button class="primary" type="submit" :disabled="!form.name.trim() || !form.base_url.trim() || !!pickerMode">保存连接</button><button type="button" :disabled="!selected || connectionDirty || !selected.enabled || !!pickerMode" @click="discover">获取模型列表</button><button v-if="selected" class="danger" type="button" :disabled="!!pickerMode" @click="remove">删除连接</button></div>
            </fieldset>
          </form>
          <details class="compatibility-note"><summary>其他服务与模型如何接入？</summary><p>Claude 可通过 OpenRouter 等兼容平台选择，使用对应平台的 Key。Anthropic 原生接口、Azure / Bedrock 专属鉴权及编程订阅尚未直接接入。部分思考模型需要额外参数或多轮消息适配；一次连接测试不代表完整学习任务可用。</p></details>
          <details v-if="selected?.model_ids.length" class="model-tests" open>
            <summary>模型可用性 <span>{{ selected.model_ids.length }} 个模型</span></summary>
            <p class="muted">按需测试模型，可能产生服务商费用；通过测试不代表教学质量达标。</p>
            <input v-model="modelSearch" class="model-search" type="search" aria-label="搜索已保存模型" placeholder="搜索模型名称，如 qwen-plus" />
            <div v-for="model in visibleModels" :key="model" class="model-row"><div><strong>{{ model }}</strong><small :class="{ success: selected.checks[model]?.ok }">{{ selected.checks[model] ? (selected.checks[model]!.ok ? `工具调用通过 · ${selected.checks[model]!.latency_ms} ms` : '测试未通过') : '尚未测试' }}</small></div><button :disabled="busy || dirty || !selected.enabled" @click="probe(model)">测试连接</button></div>
            <p v-if="!matchingModels.length" role="status">没有匹配的模型，请尝试其他名称。</p>
            <nav v-else class="model-pagination" aria-label="模型列表分页">
              <small aria-live="polite">共 {{ matchingModels.length }} 项 · {{ currentModelPage }} / {{ modelPageCount }} 页</small>
              <div><button :disabled="currentModelPage === 1" @click="modelPage = currentModelPage - 1">上一页</button><button :disabled="currentModelPage === modelPageCount" @click="modelPage = currentModelPage + 1">下一页</button></div>
            </nav>
          </details>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.picker-filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}.picker-filters button{padding:6px 8px;font-size:11px}.picker-filters [aria-pressed="true"]{background:var(--color-brand-soft);border-color:var(--color-brand-strong)}.picker-guide{font-size:11px;margin:6px 0 10px}.picker-warning{background:#fff5db;padding:8px;border-radius:6px}.picker-versions summary{cursor:pointer;font-size:11px;color:var(--color-brand-strong);padding:7px 4px}.picker-versions{padding-left:12px}

.model-picker-list{max-height:240px;max-height:min(240px,32dvh);overflow-y:auto;overscroll-behavior-y:contain;scrollbar-gutter:stable;touch-action:pan-y;border-block:1px solid var(--color-border)}.model-picker-list:focus-visible{outline:2px solid var(--color-brand-strong);outline-offset:2px}.model-picker-list .model-picker-row:last-child{border-bottom:0}
.model-selection-summary,.picker-selection-count{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--color-ink-muted);margin:0 0 16px}.model-picker{padding:18px;margin-bottom:20px;border:1px solid var(--color-border);border-radius:10px;background:var(--color-surface,#fff)}.model-picker h3{margin-top:0}.picker-selection-count{margin:12px 0 4px}.picker-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
.route-fields :deep(.el-select){width:100%;min-width:0}.route-fields :deep(.el-select__wrapper){min-height:42px;font-weight:400}.route-fields :deep(.el-select__input){padding:0;border:0;box-shadow:none;outline:none}.route-fields :deep(.el-select__placeholder){font-size:13px}
.model-tests summary{cursor:pointer;font-size:15px;font-weight:600;padding:8px 0}.model-tests summary span{font-size:12px;font-weight:400;color:var(--color-ink-muted);margin-left:10px}.model-search{margin:4px 0 6px}.model-pagination{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding-top:14px}.model-pagination>div{display:flex;gap:8px}
.preset-fields{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr);gap:16px}.preset-note{margin:0 0 20px;padding:12px 14px;background:var(--color-brand-soft);border-radius:8px;overflow-wrap:anywhere}.preset-note a{color:var(--color-brand-strong);white-space:nowrap}.model-suggestions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:-4px 0 12px;min-width:0}.model-suggestions span{font-size:12px;color:var(--color-ink-muted)}.model-suggestions button{overflow-wrap:anywhere;max-width:100%;text-align:left}.compatibility-note{margin-top:18px;font-size:12px;color:var(--color-ink-muted)}.compatibility-note summary{cursor:pointer}.compatibility-note p{margin-bottom:0}@media(max-width:800px){.preset-fields{grid-template-columns:1fr;gap:0}}
.model-page{max-width:1200px;margin:0 auto;padding:36px 24px 64px;color:var(--color-ink)}
.panel{background:var(--color-surface,#fff);border:1px solid var(--color-border);border-radius:14px;padding:26px}
.routing{margin:24px 0}.eyebrow{font-size:11px;font-weight:750;letter-spacing:.14em;color:var(--color-brand-strong)}h2{font-size:19px;margin:8px 0 12px}h3{font-size:15px}p,small{color:var(--color-ink-muted);line-height:1.6}p{font-size:13px}small{font-size:12px}.route-fields,.form-pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}.route-fields{margin:22px 0}.connection-layout{display:grid;grid-template-columns:300px minmax(0,1fr);gap:22px;align-items:start}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:16px}.section-heading h2{margin:0}.section-heading h2 span{font-size:12px;color:var(--color-ink-muted);margin-left:6px}.connection-list{padding:20px}.connection-card{width:100%;display:grid;text-align:left;gap:7px;margin-top:10px;padding:16px;border-radius:10px;overflow-wrap:anywhere}.connection-card strong{font-size:14px}.connection-card span{font-size:12px;color:var(--color-ink-muted)}.connection-card.selected{border-color:var(--color-brand-strong);background:var(--color-brand-soft)}.protocol{font-size:11px;color:var(--color-ink-muted);text-align:right}fieldset{border:0;padding:0;margin:0;min-width:0}label{display:grid;gap:8px;font-size:13px;font-weight:600;margin-bottom:18px;min-width:0}input,select,textarea{width:100%;min-width:0;box-sizing:border-box;padding:11px 12px;border:1px solid var(--color-border);border-radius:7px;background:#fff;color:var(--color-ink);font:inherit;font-weight:400}textarea{resize:vertical;font-family:monospace}input:focus,select:focus,textarea:focus{outline:2px solid var(--color-brand-strong);outline-offset:2px}.check-row{display:flex;gap:24px;flex-wrap:wrap}.check-row label{display:flex;align-items:center;font-weight:400}.check-row input{width:auto}.actions{display:flex;gap:10px;flex-wrap:wrap}button{border:1px solid var(--color-border);border-radius:7px;padding:9px 13px;background:#fff;color:var(--color-ink);font:inherit;font-size:12px;cursor:pointer}button.primary{background:var(--color-ink);border-color:var(--color-ink);color:#fff}button:disabled{opacity:.5;cursor:not-allowed}.danger{color:#b42318}.feedback{padding:12px 16px;border-radius:8px;background:var(--color-brand-soft);overflow-wrap:anywhere}.error{background:#fff1f0;color:#b42318}.model-tests{margin-top:26px;border-top:1px solid var(--color-border);padding-top:12px}.model-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 0;border-bottom:1px solid var(--color-border)}.model-row>div{display:grid;gap:5px;min-width:0}.model-row strong{font-size:13px;overflow-wrap:anywhere}.model-row button{flex-shrink:0}.success{color:#18794e}
@media(max-width:800px){.connection-layout{grid-template-columns:1fr}.route-fields,.form-pair{grid-template-columns:1fr;gap:0}.model-page{padding:24px 16px 40px}.panel{padding:20px}.section-heading{align-items:flex-start}.protocol{max-width:130px}}
</style>
