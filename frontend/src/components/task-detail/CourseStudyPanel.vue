<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CourseChaptersPanel from "../CourseChaptersPanel.vue";
import type { AnalysisTaskStatus } from "../../types/task";
import type { TaskResultResponse } from "../../types/result";

type StudyView = "summary" | "chapters" | "glossary";
const props = defineProps<{ taskId: string; status?: AnalysisTaskStatus; result: TaskResultResponse | null }>();
defineEmits<{ seek: [startTimeMillis: number] }>();
const activeView = ref<StudyView>("summary");
const learning = computed(() => props.result?.learningPackage ?? null);
const emptyDescription = computed(() => props.status === "FAILED" ? "处理失败，未生成学习资料" : props.status === "CANCELED" ? "处理已取消，未生成学习资料" : "学习资料生成中");
const views: Array<{ value: StudyView; label: string }> = [
  { value: "summary", label: "摘要与重点" },
  { value: "chapters", label: "课程章节" },
  { value: "glossary", label: "术语与问答" },
];

watch(() => props.taskId, () => { activeView.value = "summary"; });

function glossaryText(item: { translation?: string; definition?: string }): string {
  const translation = item.translation?.trim() || "";
  const definition = item.definition?.trim() || "";
  return translation && definition ? `${translation}：${definition}` : translation || definition || "暂无解释";
}
</script>

<template>
  <section class="workspace-panel study-panel" aria-labelledby="study-title">
    <header><h2 id="study-title">学习资料</h2><p>查看课程摘要、重点、章节和术语。</p></header>
    <nav class="subnav" aria-label="学习资料视图">
      <button v-for="item in views" :key="item.value" type="button" :aria-pressed="activeView === item.value" :class="{ 'is-active': activeView === item.value }" @click="activeView = item.value">{{ item.label }}</button>
    </nav>

    <section v-if="activeView === 'summary'" class="study-copy" aria-label="摘要与重点">
      <el-empty v-if="!learning" :description="emptyDescription" />
      <template v-else>
        <div><p class="study-label">学习资料</p><h3>{{ learning.title || "课程学习资料" }}</h3></div>
        <article><h4>课程摘要</h4><p>{{ learning.summary || "暂无课程摘要" }}</p></article>
        <article><h4>重点</h4><el-empty v-if="learning.keyPoints.length === 0" description="暂无重点内容" /><ol v-else><li v-for="point in learning.keyPoints" :key="point.index">{{ point.text }}</li></ol></article>
      </template>
    </section>

    <KeepAlive>
      <CourseChaptersPanel v-if="activeView === 'chapters'" :task-id="taskId" @seek="$emit('seek', $event)" />
    </KeepAlive>

    <section v-if="activeView === 'glossary'" class="study-reference" aria-label="术语与问答">
      <el-empty v-if="!learning" :description="emptyDescription" />
      <template v-else>
        <article><h3>术语表</h3><el-empty v-if="learning.glossary.length === 0" description="暂无术语" /><dl v-else><div v-for="item in learning.glossary" :key="item.term"><dt>{{ item.term }}</dt><dd>{{ glossaryText(item) }}</dd></div></dl></article>
        <article><h3>预生成问答</h3><el-empty v-if="learning.qa.length === 0" description="暂无预生成问答" /><dl v-else><div v-for="item in learning.qa" :key="item.question"><dt>{{ item.question }}</dt><dd>{{ item.answer }}</dd></div></dl></article>
      </template>
    </section>
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p, h3, h4 { margin: 0; } header p { color: var(--color-ink-soft); }
.subnav { display: flex; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); overflow-x: auto; }
.subnav button { flex: 0 0 auto; padding: 8px 13px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-ink-soft); font: inherit; cursor: pointer; }
.subnav button.is-active { border-color: var(--color-border); background: var(--color-brand-soft, #edf4f0); color: var(--color-brand); font-weight: 700; }
.study-copy, .study-reference { display: grid; gap: 24px; }
.study-label { margin: 0 0 6px; color: var(--color-brand); font-size: 12px; font-weight: 750; letter-spacing: .1em; }
.study-copy article, .study-reference article { display: grid; gap: 12px; padding-top: 18px; border-top: 1px solid var(--color-border); }
.study-copy p, .study-copy li, .study-reference dd { color: var(--color-ink-soft); line-height: 1.75; }
.study-copy ol { display: grid; gap: 10px; margin: 0; padding-left: 22px; }
.study-reference dl { display: grid; margin: 0; }.study-reference dl div { display: grid; grid-template-columns: minmax(120px, .32fr) minmax(0, 1fr); gap: 18px; padding: 14px 0; border-bottom: 1px solid var(--color-border); }.study-reference dt { font-weight: 700; }.study-reference dd { margin: 0; }
@media (max-width: 620px) { .study-reference dl div { grid-template-columns: 1fr; gap: 6px; } }
</style>
