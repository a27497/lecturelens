<script setup lang="ts">
import type { CourseWorkspace } from "./workspace";

defineProps<{ active: CourseWorkspace; compact?: boolean; materials?: boolean }>();
defineEmits<{ change: [workspace: CourseWorkspace] }>();

const items: Array<{ value: CourseWorkspace; label: string }> = [
  { value: "agent", label: "学习助手" },
  { value: "tutor", label: "Tutor 对话" },
  { value: "flashcards", label: "闪卡复习" },
  { value: "overview", label: "概览" },
  { value: "content", label: "课程内容" },
  { value: "study", label: "学习资料" },
  { value: "qa", label: "课程问答" },
  { value: "files", label: "下载" },
  { value: "technical", label: "处理详情" },
];
const primary = ["agent", "tutor", "qa", "flashcards"];
const isPrimary = (value: string, materials?: boolean) => primary.includes(value) || (!materials && value === "study");
function label(value: CourseWorkspace, fallback: string, compact?: boolean) {
  if (!compact) return fallback;
  return value === "content" ? "课程材料" : value === "agent" ? "解释与练习" : value === "qa" ? "课程问答" : fallback;
}
</script>

<template>
  <nav class="workspace-nav" aria-label="课程内容导航">
    <button
      v-for="item in items.filter(item => !compact || isPrimary(item.value, materials) || (materials && item.value === 'content'))"
      :key="item.value"
      type="button"
      :class="{ 'is-active': active === item.value }"
      :aria-current="active === item.value ? 'page' : undefined"
      @click="$emit('change', item.value)"
    >
      {{ label(item.value, item.label, compact) }}
    </button>
    <details v-if="compact" class="workspace-more" :open="!isPrimary(active, materials) && !(materials && active === 'content')">
      <summary>更多</summary>
      <button v-for="item in items.filter(item => !isPrimary(item.value, materials) && !(materials && item.value === 'content'))" :key="item.value" type="button" :class="{ 'is-active': active === item.value }" :aria-current="active === item.value ? 'page' : undefined" @click="$emit('change', item.value)">{{ label(item.value, item.label, compact) }}</button>
    </details>
  </nav>
</template>

<style scoped>
.workspace-nav:has(.workspace-more) { border: 0; border-bottom: 1px solid var(--color-border); padding: 0 0 8px; border-radius: 0; gap: 4px; }
.workspace-nav:has(.workspace-more) button { flex: 1 0 0; min-width: 0; padding: 10px 8px; font-size: 14px; }
.workspace-more summary { font-size: 13px; }

.workspace-nav { display: flex; gap: 4px; min-width: 0; overflow-x: auto; padding: 5px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); scrollbar-width: thin; }
.workspace-nav button { flex: 1 0 auto; padding: 10px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-ink-soft); font: inherit; font-weight: 650; cursor: pointer; }
.workspace-nav button:hover { color: var(--color-ink); background: var(--color-canvas); }
.workspace-nav button.is-active { border-color: var(--color-border-strong, var(--color-border)); background: var(--color-brand-soft, #edf4f0); color: var(--color-brand-strong, var(--color-brand)); }
.workspace-more { flex: 1 0 auto; }.workspace-more summary { cursor: pointer; padding: 10px; color: var(--color-ink-soft); }.workspace-more[open] { flex-basis: 100%; }
.workspace-nav:has(.workspace-more) { flex-wrap: wrap; overflow: visible; }
</style>
