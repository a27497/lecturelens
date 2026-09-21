// Official descriptions checked 2026-09-17; links are retained with each entry.
// Display guidance only: never used to authorize or certify a model.
export interface ModelGuide {
  category: "candidate" | "other" | "unknown";
  label: string;
  description: string;
  source?: string;
  capability?: string;
}
const docs = "https://help.aliyun.com/zh/model-studio/";
const known: Record<string, Omit<ModelGuide, "category">> = {
  "qwen-plus": { label: "通用对话", description: "通用文本任务候选；默认不开启思考。", source: "deep-thinking" },
  "qwen3-max": { label: "通用对话", description: "复杂文本任务候选；默认不开启思考。", source: "deep-thinking" },
  "qwen-flash": { label: "通用对话", description: "日常流程调试候选；默认不开启思考。", source: "deep-thinking" },
  "qwen3.8-max": { label: "通用多模态", description: "Max 旗舰系列；默认开启思考，需验证调用适配。", source: "text-generation-model", capability: "官方支持工具调用" },
  "qwen3.8-max-0902": { label: "通用多模态", description: "9 月 2 日固定快照；适合固定版本对比，需验证调用适配。", source: "newly-released-models" },
  "qwen3.8-flash": { label: "通用多模态", description: "侧重速度与成本；默认开启思考，需验证调用适配。", source: "text-generation-model", capability: "官方支持工具调用" },
  "qwen3.8-27b": { label: "通用多模态", description: "270 亿参数；支持图文和视频理解。", source: "qwen3-8-27b", capability: "官方支持工具调用" },
  "qwen3.8-2.4t-a95b": { label: "通用文本", description: "开源 MoE：总参数 2.4 万亿，激活约 950 亿；需验证思考适配。", source: "qwen3-8-2-4t-a95b", capability: "官方支持工具调用" },
  "qwen3.8-omni-flash": { label: "全模态", description: "理解图文、音频和视频，输出文字；当前学习流程未直接传入音视频。", source: "qwen3-8-omni-flash", capability: "官方支持工具调用" },
};
export function modelGuide(id: string, bailian = false): ModelGuide {
  if (bailian && known[id]) return { category: "candidate", ...known[id], source: docs + known[id].source };
  const name = id.toLowerCase();
  // Conservative naming hints, not claims about provider-specific capabilities.
  const specialized: [RegExp, string, string][] = [
    [/embedding|(?:^|[/_-])embed(?:$|[/_-])/, "向量检索", "用于文本向量化，通常不用于决策或草稿复核。"],
    [/rerank/, "检索排序", "用于检索结果重排，通常不用于生成答案。"],
    [/livetranslate|(?:^|[/_-])mt(?:$|[/_-])/, "翻译", "偏向翻译任务；当前决策与复核用途不优先。"],
    [/realtime|(?:^|[/_-])(?:tts|asr|audio)(?:$|[/_-])|speech|transcri/, "语音／实时", "偏向语音或实时接口，需单独确认接入方式。"],
    [/(?:^|[/_-])(?:wan\d*|flux|dall-e|stable-diffusion|image-generation)(?:$|[/_.-])/, "图像／视频生成", "用于生成图像或视频，当前学习助手不使用此用途。"],
  ];
  for (const [pattern, label, description] of specialized) {
    if (pattern.test(name)) return { category: "other", label, description: description + "（按名称判断）" };
  }
  return { category: "unknown", label: "用途待识别", description: "尚无核实的用途资料；请查看服务商说明并测试工具调用。" };
}
export function snapshotFamily(id: string): string {
  return id.replace(/-(?:20\d{2}-\d{2}-\d{2}|20\d{6}|(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))$/, "");
}
export function groupModelVersions(ids: string[], expand: boolean) {
  if (expand) return ids.map(id => ({ id, versions: [] as string[] }));
  const families = new Map<string, string[]>();
  for (const id of ids) {
    const family = snapshotFamily(id);
    families.set(family, [...(families.get(family) ?? []), id]);
  }
  return [...families].map(([family, items]) => {
    // Keep the exact provider ID; never invent an alias or merge selection state.
    const id = items.includes(family) ? family : [...items].sort().at(-1)!;
    return { id, versions: items.filter(item => item !== id) };
  });
}
