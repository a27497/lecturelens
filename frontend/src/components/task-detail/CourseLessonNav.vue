<script setup lang="ts">
import { ChatDotRound, CircleCheck, Collection, Document } from "@element-plus/icons-vue";
import type { CourseWorkspace } from "./workspace";

defineProps<{ active?: CourseWorkspace; mobile?: boolean }>();
const emit = defineEmits<{ change: [workspace: CourseWorkspace] }>();
const tabs = [
  { value: "content", title: "课程", icon: Collection },
  { value: "tutor", title: "助手", desktop: "对话", icon: ChatDotRound },
  { value: "notes", title: "笔记", icon: Document },
  { value: "agent", title: "练习", icon: CircleCheck },
] as const;
</script>
<template>
  <nav class="lesson-nav" :class="{ 'lesson-nav--mobile': mobile }" aria-label="课程学习导航">
    <template v-for="tab in tabs" :key="tab.value">
      <button v-if="mobile || tab.value !== 'content'" type="button" :aria-pressed="active === tab.value"
        @click="emit('change', tab.value)">
        <component v-if="mobile" :is="tab.icon" aria-hidden="true" />
        {{ !mobile && 'desktop' in tab ? tab.desktop : tab.title }}
      </button>
    </template>
  </nav>
</template>
<style scoped>
.lesson-nav { display: flex; gap: 24px; align-items: stretch; border-bottom: 1px solid var(--color-border); }
button { border: 0; border-bottom: 2px solid transparent; background: none; color: var(--color-ink-soft); font: inherit; padding: 9px 4px; cursor: pointer; }
button[aria-pressed="true"] { border-color: var(--color-brand); color: var(--color-brand); font-weight: 750; }
.lesson-nav--mobile { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; }
.lesson-nav--mobile button { display: flex; align-items: center; justify-content: center; gap: 5px; min-height: 46px; font-size: 14px; }
svg { width: 16px; height: 16px; }
</style>
