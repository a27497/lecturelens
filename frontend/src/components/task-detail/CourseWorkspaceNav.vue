<script setup lang="ts">
import { computed, ref } from "vue";
import type { CourseWorkspace } from "./workspace";
import { WORKSPACE_ITEMS as items, workspaceLabel } from "./workspace";

const props = defineProps<{ active: CourseWorkspace; compact?: boolean; materials?: boolean }>();
const emit = defineEmits<{ change: [workspace: CourseWorkspace] }>();
const menu = ref<HTMLDetailsElement | null>(null);
const learningModes: CourseWorkspace[] = ["tutor", "notes", "agent", "flashcards"];
const primary = computed(() => !props.compact ? items.map(item => item.value) :
  props.materials ? ["content" as const, ...learningModes] : learningModes);
const secondary = computed(() => items.map(item => item.value).filter(value => !primary.value.includes(value)));

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
  <nav class="workspace-nav" :class="{ 'workspace-nav--compact': compact }" aria-label="课程内容导航">
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
      <summary :aria-label="secondary.includes(active) ? `更多，当前：${workspaceLabel(active, compact)}` : undefined" :class="{ 'is-active': secondary.includes(active) }">
        {{ secondary.includes(active) ? workspaceLabel(active, compact) : '更多' }}
      </summary>
      <div class="workspace-more__items">
        <button v-for="value in secondary" :key="value" type="button" :aria-current="active === value ? 'page' : undefined" @click="choose(value, true)">
          {{ workspaceLabel(value, compact) }}
        </button>
      </div>
    </details>
  </nav>
</template>

<style scoped>
.workspace-nav { display: flex; gap: 4px; min-width: 0; overflow-x: auto; padding: 5px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); scrollbar-width: thin; }
.workspace-nav button, .workspace-more summary { flex: 0 0 auto; padding: 8px 10px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--color-ink-soft); font: inherit; font-weight: 650; cursor: pointer; }
.workspace-nav button:hover, .workspace-more summary:hover { color: var(--color-ink); background: var(--color-canvas); }
.workspace-nav button[aria-current], .workspace-more summary.is-active { background: var(--color-brand-soft); color: var(--color-brand-strong); }
.workspace-nav--compact { position: relative; align-items: center; flex-wrap: wrap; overflow: visible; padding: 0 0 10px; border: 0; border-bottom: 1px solid var(--color-border); border-radius: 0; font-size: 14px; }
.workspace-more__items { position: absolute; z-index: 12; inset-block-start: 100%; inset-inline-end: 0; display: grid; min-width: max-content; padding: 6px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); box-shadow: var(--shadow-low); }
.workspace-more__items button { text-align: start; }
@media (max-width: 1024px) {
  .workspace-nav--compact button, .workspace-more summary { min-height: 44px; padding: 10px 7px; font-size: 13px; }
}
</style>
