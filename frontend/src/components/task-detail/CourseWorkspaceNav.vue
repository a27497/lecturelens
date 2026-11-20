<script setup lang="ts">
import { computed, ref } from "vue";
import type { CourseWorkspace } from "./workspace";
import { LEARNING_MODES, WORKSPACE_ITEMS as items, workspaceLabel } from "./workspace";

const props = defineProps<{ active: CourseWorkspace; compact?: boolean; materials?: boolean; resumeWorkspace?: CourseWorkspace }>();
const emit = defineEmits<{ change: [workspace: CourseWorkspace]; resume: [] }>();
const menu = ref<HTMLDetailsElement | null>(null);
const resume = computed(() => props.materials && props.active === "content" ? props.resumeWorkspace : undefined);
const primaryModes: readonly CourseWorkspace[] = LEARNING_MODES;
const primary = computed(() => props.compact ? primaryModes.filter(value => value !== resume.value) : items.map(item => item.value));
const extras = computed(() => items.map(item => item.value).filter(value =>
  !primaryModes.includes(value) && value !== resume.value && (!props.materials || value !== "content")));

function choose(workspace: CourseWorkspace, fromMenu = false) {
  if (menu.value?.open) {
    menu.value.open = false;
    if (fromMenu) menu.value.querySelector("summary")?.focus();
  }
  emit("change", workspace);
}

function closeOnEscape(event: KeyboardEvent) {
  if (!menu.value?.open) return;
  event.preventDefault();
  menu.value.open = false;
  menu.value.querySelector("summary")?.focus();
}
</script>

<template>
  <nav class="workspace-nav" :class="{ 'workspace-nav--compact': compact, 'workspace-nav--narrow': materials }" aria-label="课程内容导航">
    <div v-if="materials" class="workspace-selector">
      <button type="button" class="workspace-materials" :aria-current="active === 'content' ? 'page' : undefined" @click="choose('content')">课程材料</button>
      <button v-if="resume" class="workspace-resume" type="button" @click="emit('resume')">返回 {{ workspaceLabel(resume) }} <span aria-hidden="true">↗</span></button>
      <span v-else class="workspace-selector__label">学习工作台</span>
    </div>
    <div class="workspace-modes">
    <button
      v-for="value in primary"
      :key="value"
      type="button"
      :aria-current="active === value ? 'page' : undefined"
      @click="choose(value)"
    >
      {{ workspaceLabel(value, compact) }}
    </button>
    <details v-if="compact" ref="menu" class="workspace-more" @keydown.esc="closeOnEscape">
      <summary :aria-label="extras.includes(active) ? `更多，当前：${workspaceLabel(active, compact)}` : undefined" :class="{ 'is-active': extras.includes(active) }">
        {{ extras.includes(active) ? workspaceLabel(active, compact) : '更多' }}
      </summary>
      <div class="workspace-more__items">
        <button v-for="value in extras" :key="value" type="button" :aria-current="active === value ? 'page' : undefined" @click="choose(value, true)">
          {{ workspaceLabel(value, compact) }}
        </button>
      </div>
    </details>
    </div>
  </nav>
</template>

<style scoped>
.workspace-nav { min-width: 0; overflow-x: auto; padding: 5px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); scrollbar-width: thin; }
.workspace-modes, .workspace-selector { display: flex; align-items: center; gap: 4px; }
.workspace-nav button, .workspace-more summary { flex: 0 0 auto; padding: 8px 10px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--color-ink-soft); font: inherit; font-weight: 650; cursor: pointer; }
.workspace-nav button:hover, .workspace-more summary:hover { color: var(--color-ink); background: var(--color-canvas); }
.workspace-nav button[aria-current], .workspace-more summary.is-active { background: var(--color-brand-soft); color: var(--color-brand-strong); }
.workspace-nav--compact { position: relative; overflow: visible; padding: 0; border: 0; background: transparent; font-size: 14px; }
.workspace-nav--compact .workspace-modes { flex-wrap: wrap; }
.workspace-nav--compact .workspace-modes > button[aria-current] { border-color: var(--color-border-strong); background: var(--color-surface); }
.workspace-nav--narrow { padding: 4px 6px; border: 1px solid var(--color-border-strong); border-radius: var(--radius-md); background: var(--color-surface); }
.workspace-selector { justify-content: space-between; border-bottom: 1px solid var(--color-border); }
.workspace-selector .workspace-materials { color: var(--color-brand-strong); border-inline-end-color: var(--color-border); border-radius: 0; }
.workspace-selector__label { padding-inline: 8px; color: var(--color-ink-soft); font-weight: 650; }
.workspace-selector .workspace-resume { min-width: 0; color: var(--color-brand-strong); }
.workspace-more__items { position: absolute; z-index: 12; inset-block-start: 100%; inset-inline-end: 0; display: grid; min-width: max-content; padding: 6px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); box-shadow: var(--shadow-low); }
.workspace-more__items button { text-align: start; }
@media (max-width: 1024px) {
  .workspace-nav--compact button, .workspace-more summary { min-height: 44px; padding: 10px 7px; font-size: 13px; }
  .workspace-nav--narrow .workspace-modes { justify-content: space-between; }
}
</style>
