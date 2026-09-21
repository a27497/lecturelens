import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import { ElSelect } from "element-plus";
import ModelManagementView from "./ModelManagementView.vue";
import { modelCommand, type ModelCatalog } from "../api/models";

vi.mock("../api/models", async importOriginal => ({ ...await importOriginal<typeof import("../api/models")>(), modelCommand: vi.fn() }));
const catalog: ModelCatalog = {
  presets: [
    { id: "bailian-beijing", name: "阿里云百炼 · 北京", group: "国内服务", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen-plus", "qwen-flash"], note: "使用同地域的普通 API Key", docs_url: "https://help.aliyun.com/en/model-studio/base-url" },
    { id: "openai", name: "OpenAI", group: "国际服务", base_url: "https://api.openai.com/v1", models: ["gpt-4.1"], note: "使用 API Key", docs_url: "https://developers.openai.com/api/docs/models/gpt-4.1" },
  ],
  connections: [{ connection_id: "mine", name: "我的模型", base_url: "http://127.0.0.1:8091/v1", model_ids: ["generator", "critic"], enabled: true, version: 3, has_key: true, checks: {} }],
  bindings: { decision: { connection_id: "mine", model: "generator" }, review: { connection_id: "mine", model: "critic" } },
  environment: { available: false, model: "", mode: "real" },
};
beforeEach(() => { vi.resetAllMocks(); vi.mocked(modelCommand).mockResolvedValue(structuredClone(catalog)); });

it("restores per-user connections and saves edits without re-sending a blank credential", async () => {
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe("");
  expect(wrapper.get('input[type="password"]').attributes("placeholder")).toContain("已保存密钥");
  vi.mocked(modelCommand).mockResolvedValueOnce({ connection_id: "mine" }).mockResolvedValueOnce(catalog);
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  const saved = vi.mocked(modelCommand).mock.calls.find(([c]) => c.operation === "SAVE")![0];
  expect(saved).toMatchObject({ connection_id: "mine", version: 3, connection: { model_ids: ["generator", "critic"] } });
  expect(saved.connection).not.toHaveProperty("api_key");
  expect(saved).not.toHaveProperty("owner_id");
  wrapper.unmount();
});

it("allows distinct decision and review models and only applies them on explicit save", async () => {
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  wrapper.findAllComponents(ElSelect)[0]!.vm.$emit("update:modelValue", JSON.stringify(["mine", "critic"]));
  expect(vi.mocked(modelCommand).mock.calls).toHaveLength(1);
  vi.mocked(modelCommand).mockResolvedValueOnce({ saved: true });
  await wrapper.findAll("button").find(b => b.text() === "保存模型用途")!.trigger("click");
  await flushPromises();
  expect(vi.mocked(modelCommand).mock.calls.at(-1)![0]).toEqual({ operation: "ROUTE", bindings: { decision: { connection_id: "mine", model: "critic" }, review: { connection_id: "mine", model: "critic" } } });
  expect(wrapper.text()).toContain("新创建的 Agent 运行");
  wrapper.unmount();
});

it("only adds explicitly selected discoveries and requires saving before routing them", async () => {
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  vi.mocked(modelCommand).mockResolvedValueOnce({ model_ids: Array.from({ length: 80 }, (_, i) => `new-model-${i}`) });
  await wrapper.findAll("button").find(b => b.text() === "获取模型列表")!.trigger("click");
  await flushPromises();
  expect(wrapper.get("textarea").element.value).toBe("generator\ncritic");
  expect(wrapper.findAll('.model-picker input[type="checkbox"]')).toHaveLength(80);
  expect(wrapper.findAll("button").find(b => b.text() === "添加所选（0）")!.attributes("disabled")).toBeDefined();
  await wrapper.get('[aria-label="搜索待选模型"]').setValue("new-model-79");
  await wrapper.get('.model-picker input[type="checkbox"]').setValue(true);
  await wrapper.findAll("button").find(b => b.text() === "添加所选（1）")!.trigger("click");
  expect(wrapper.get("textarea").element.value).toBe("generator\ncritic\nnew-model-79");
  expect(wrapper.text()).toContain("请保存连接后使用");
  expect(wrapper.findAll("button").filter(b => b.text() === "测试连接").every(b => b.attributes("disabled") !== undefined)).toBe(true);
  expect(vi.mocked(modelCommand).mock.calls.map(([c]) => c.operation)).toEqual(["LIST", "DISCOVER"]);
  vi.mocked(modelCommand).mockResolvedValueOnce({ connection_id: "mine" }).mockResolvedValueOnce(catalog);
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(vi.mocked(modelCommand).mock.calls.find(([c]) => c.operation === "SAVE")![0].connection).toMatchObject({ model_ids: ["generator", "critic", "new-model-79"] });
  wrapper.unmount();
});

it("cancels discovery without editing IDs and trims existing lists without removing bound models", async () => {
  const many = structuredClone(catalog);
  many.connections[0]!.model_ids.push(...Array.from({ length: 78 }, (_, i) => `extra-${i}`));
  vi.mocked(modelCommand).mockResolvedValueOnce(many);
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  const original = wrapper.get("textarea").element.value;
  vi.mocked(modelCommand).mockResolvedValueOnce({ model_ids: ["unselected"] });
  await wrapper.findAll("button").find(b => b.text() === "获取模型列表")!.trigger("click");
  await flushPromises();
  await wrapper.findAll("button").find(b => b.text() === "取消")!.trigger("click");
  expect(wrapper.get("textarea").element.value).toBe(original);
  await wrapper.findAll("button").find(b => b.text() === "整理已添加模型")!.trigger("click");
  await wrapper.findAll("button").find(b => b.text() === "清空选择")!.trigger("click");
  expect(wrapper.get('.model-picker input[value="generator"]').attributes("disabled")).toBeDefined();
  await wrapper.findAll("button").find(b => b.text() === "保留所选（2）")!.trigger("click");
  expect(wrapper.get("textarea").element.value).toBe("generator\ncritic");
  expect(vi.mocked(modelCommand).mock.calls.map(([c]) => c.operation)).toEqual(["LIST", "DISCOVER"]);
  wrapper.unmount();
});

it("reports a concurrent-edit conflict without clearing the user's draft", async () => {
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  await wrapper.get('input[type="url"]').setValue("https://api.deepseek.com/v1");
  await wrapper.get('input[type="password"]').setValue("new-private-key");
  vi.mocked(modelCommand).mockRejectedValueOnce({ response: { data: { message: "MODEL_VERSION_CONFLICT" } } });
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("其他页面修改");
  expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe("new-private-key");
  expect(wrapper.text()).not.toContain("new-private-key");
  wrapper.unmount();
});

it("starts a clean preset draft without transferring a saved connection or typed key", async () => {
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  await wrapper.get('input[type="password"]').setValue("do-not-transfer-this-key");
  await wrapper.get("form select").setValue("bailian-beijing");
  expect((wrapper.get('input[type="url"]').element as HTMLInputElement).value).toBe("https://dashscope.aliyuncs.com/compatible-mode/v1");
  expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe("");
  expect(wrapper.get("textarea").element.value).toBe("");
  expect(vi.mocked(modelCommand).mock.calls).toHaveLength(1);
  await wrapper.findAll("button").find(b => b.text() === "＋ qwen-plus")!.trigger("click");
  expect(wrapper.get("textarea").element.value).toBe("qwen-plus");
  expect(wrapper.findAll("button").find(b => b.text() === "已添加 · qwen-plus")!.attributes("disabled")).toBeDefined();
  vi.mocked(modelCommand).mockResolvedValueOnce({ connection_id: "new" }).mockResolvedValueOnce(catalog);
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  const saved = vi.mocked(modelCommand).mock.calls.find(([c]) => c.operation === "SAVE")![0];
  expect(saved).not.toHaveProperty("connection_id");
  expect(saved.connection).toMatchObject({ name: "阿里云百炼 · 北京", model_ids: ["qwen-plus"] });
  expect(saved.connection).not.toHaveProperty("api_key");
  wrapper.unmount();
});

it("filters grouped presets by model and preserves manual IDs when adding suggestions", async () => {
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  await wrapper.get('input[type="search"]').setValue("GPT");
  expect(wrapper.get("form select").text()).toContain("OpenAI");
  expect(wrapper.get("form select").text()).not.toContain("百炼");
  await wrapper.get("form select").setValue("openai");
  await wrapper.get("textarea").setValue("my-deployment");
  await wrapper.findAll("button").find(b => b.text() === "＋ gpt-4.1")!.trigger("click");
  expect(wrapper.get("textarea").element.value).toBe("my-deployment\ngpt-4.1");
  await wrapper.get('input[type="url"]').setValue("https://custom.example/v1");
  expect(wrapper.find('[aria-label="常用模型快捷添加"]').exists()).toBe(false);
  expect(vi.mocked(modelCommand).mock.calls).toHaveLength(1);
  wrapper.unmount();
});

it("filters specialist models, reveals exact snapshots in search and preserves hidden selections", async () => {
  const bailian = structuredClone(catalog);
  bailian.connections[0]!.base_url = bailian.presets![0]!.base_url;
  vi.mocked(modelCommand).mockResolvedValueOnce(bailian);
  const wrapper = mount(ModelManagementView);
  await flushPromises();
  vi.mocked(modelCommand).mockResolvedValueOnce({
    model_ids: ["qwen3.8-max", "qwen3.8-max-0902", "qwen3.8-flash", "text-embedding-v4", "private-deployment"],
    total_count: 1005, truncated: true, skipped_count: 1,
  });
  await wrapper.findAll("button").find(b => b.text() === "获取模型列表")!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("目录未完整展示");
  expect(wrapper.find('.model-picker input[value="text-embedding-v4"]').exists()).toBe(false);
  expect(wrapper.find('.model-picker input[value="private-deployment"]').exists()).toBe(true);
  expect(wrapper.get('.picker-versions').attributes("open")).toBeUndefined();
  expect(wrapper.text()).toContain("官方支持工具调用");
  expect(wrapper.text()).toContain("本项目未测试");
  await wrapper.get('[aria-label="搜索待选模型"]').setValue("0902");
  expect(wrapper.find('.picker-versions').exists()).toBe(false);
  await wrapper.get('.model-picker input[value="qwen3.8-max-0902"]').setValue(true);
  await wrapper.get('[aria-label="搜索待选模型"]').setValue("");
  await wrapper.findAll("button").find(b => b.text() === "其他用途（1）")!.trigger("click");
  expect(wrapper.findAll('.model-picker input[type="checkbox"]')).toHaveLength(1);
  expect(wrapper.text()).toContain("向量检索");
  await wrapper.findAll("button").find(b => b.text() === "添加所选（1）")!.trigger("click");
  expect(wrapper.get("textarea").element.value).toBe("generator\ncritic\nqwen3.8-max-0902");
  expect(vi.mocked(modelCommand).mock.calls.map(([c]) => c.operation)).toEqual(["LIST", "DISCOVER"]);
  wrapper.unmount();
});
