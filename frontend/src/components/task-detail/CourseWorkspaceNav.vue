<script setup lang="ts">
import type { CourseWorkspace } from "./workspace";

defineProps<{ active: CourseWorkspace }>();
defineEmits<{ change: [workspace: CourseWorkspace] }>();

const items: Array<{ value: CourseWorkspace; label: string }> = [
  { value: "overview", label: "概览" },
  { value: "content", label: "课程内容" },
  { value: "study", label: "学习资料" },
  { value: "qa", label: "课程问答" },
  { value: "files", label: "下载" },
  { value: "technical", label: "处理详情" },
];
</script>

<template>
  <nav class="workspace-nav" aria-label="课程内容导航">
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      :class="{ 'is-active': active === item.value }"
      :aria-current="active === item.value ? 'page' : undefined"
      @click="$emit('change', item.value)"
    >
      {{ item.label }}
    </button>
  </nav>
</template>

<style scoped>
.workspace-nav { display: flex; gap: 4px; min-width: 0; overflow-x: auto; padding: 5px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); scrollbar-width: thin; }
.workspace-nav button { flex: 1 0 auto; padding: 10px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-ink-soft); font: inherit; font-weight: 650; cursor: pointer; }
.workspace-nav button:hover { color: var(--color-ink); background: var(--color-canvas); }
.workspace-nav button.is-active { border-color: var(--color-border-strong, var(--color-border)); background: var(--color-brand-soft, #edf4f0); color: var(--color-brand-strong, var(--color-brand)); }
</style>
