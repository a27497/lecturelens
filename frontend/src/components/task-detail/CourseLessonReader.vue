<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import CourseChaptersPanel from "../CourseChaptersPanel.vue";
import type { TaskResultResponse } from "../../types/result";
import { formatMillisToClock } from "../../utils/time";
import { createTimeIndex } from "../../utils/timeIndex";

const props = defineProps<{ taskId: string; result: TaskResultResponse | null; position: number;
  loading: boolean; error: string; mobile: boolean; visible: boolean }>();
const emit = defineEmits<{ seek: [milliseconds: number]; ask: [milliseconds: number]; retry: [] }>();
const bilingual = ref(false);
const chaptersOpen = ref(false);
const following = ref(true);
const list = ref<HTMLElement>();
const rows = computed(() => {
  const translations = new Map((props.result?.translations ?? []).map(row => [row.segmentIndex, row]));
  return (props.result?.subtitles ?? []).map(row => {
    const translation = translations.get(row.segmentIndex);
    const aligned = translation?.startMillis === row.startMillis && translation?.endMillis === row.endMillis;
    return { ...row, translation: aligned ? translation.translatedText : undefined };
  });
});
const index = computed(() => createTimeIndex(rows.value, row => row.startMillis, row => row.endMillis));
const current = computed(() => index.value(props.position));
const clock = (time: number) => formatMillisToClock(time).replace(/^00:/, "");
async function showCurrent() {
  await nextTick();
  if (!following.value || !props.visible) return;
  const selected = list.value?.querySelector<HTMLElement>('[data-current="true"]');
  if (selected && list.value) list.value.scrollTop = selected.offsetTop;
}
watch([current, () => props.visible], showCurrent, { flush: "post" });
function seek(milliseconds: number) {
  following.value = true;
  emit("seek", milliseconds);
  void showCurrent();
}
</script>
<template>
  <div class="lesson-reader">
    <section class="lesson-transcript" aria-labelledby="lesson-transcript-title">
      <header>
        <h2 id="lesson-transcript-title">字幕</h2>
        <div class="language" aria-label="字幕语言">
          <button type="button" :aria-pressed="!bilingual" @click="bilingual = false">中文</button>
          <button type="button" :aria-pressed="bilingual" @click="bilingual = true">双语</button>
        </div>
      </header>
      <el-skeleton v-if="loading && !rows.length" :rows="3" animated aria-label="正在加载字幕" />
      <p v-else-if="error" role="alert">字幕暂时无法加载。 <button type="button" @click="emit('retry')">重试加载</button></p>
      <p v-else-if="!rows.length" role="status">{{ result ? '这节课暂时没有可用字幕。' : '正在准备字幕…' }}</p>
      <template v-if="rows.length">
        <div ref="list" class="lesson-transcript__list" tabindex="0" aria-label="课程字幕片段"
          @wheel.passive="following = false" @touchmove.passive="following = false"
          @keydown.up="following = false" @keydown.down="following = false">
          <article v-for="row in rows" :key="row.segmentIndex" :data-current="row === current">
            <button type="button" class="timestamp" :aria-label="`回看 ${clock(row.startMillis)}`"
              @click="seek(row.startMillis)">{{ clock(row.startMillis) }}</button>
            <div>
              <p v-if="row.translation">{{ row.translation }}</p>
              <p v-if="bilingual || !row.translation" class="transcript-original" :lang="row.language || undefined">{{ row.sourceText }}</p>
              <button v-if="row === current" type="button" class="ask" @click="emit('ask', row.startMillis)">✧ 问这一段</button>
            </div>
          </article>
        </div>
        <button v-if="!following" type="button" class="resume" @click="following = true; showCurrent()">跟随播放</button>
      </template>
    </section>
    <div class="lesson-chapters">
      <button v-if="mobile" type="button" class="chapters-toggle" :aria-expanded="chaptersOpen" @click="chaptersOpen = !chaptersOpen">
        {{ chaptersOpen ? '收起章节' : '☷　查看全部章节' }} <span aria-hidden="true">{{ chaptersOpen ? '⌄' : '›' }}</span>
      </button>
      <CourseChaptersPanel compact :position="position" :task-id="taskId" v-show="!mobile || chaptersOpen" @seek="seek" />
    </div>
  </div>
</template>
<style scoped>
.lesson-reader { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: 20px; margin-top: 28px; }
.lesson-transcript { min-width: 0; }
header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 9px; }
h2 { font-size: 18px; margin: 0; }
.language { display: flex; padding: 2px; border-radius: 7px; background: var(--color-surface-subtle); }
button { color: var(--color-brand); font: inherit; cursor: pointer; border: 0; background: transparent; }
.language button { font-size: 13px; padding: 2px 9px; border-radius: 5px; }
.language button[aria-pressed="true"] { background: var(--color-surface); font-weight: 750; }
.lesson-transcript__list { position: relative; max-height: 176px; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; }
article { display: grid; grid-template-columns: 50px minmax(0, 1fr); gap: 8px; border-bottom: 1px solid var(--color-border); padding: 9px 10px; border-inline-start: 3px solid transparent; }
article[data-current="true"] { border: 0; border-inline-start: 3px solid var(--color-brand); border-radius: 10px; background: var(--color-brand-soft); }
p { margin: 0; line-height: 1.6; font-size: 14px; overflow-wrap: anywhere; }
.transcript-original { color: var(--color-ink-soft); }
.timestamp { align-self: start; justify-self: start; padding: 0; font-size: 13px; font-weight: 750; font-variant-numeric: tabular-nums; }
.ask, .resume { padding: 4px 0; font-size: 13px; }
.chapters-toggle { display: flex; justify-content: space-between; align-items: center; width: 100%; border: 1px solid var(--color-border); border-radius: 7px; padding: 10px 12px; min-height: 44px; font-weight: 650; }
@media (max-width: 1024px) {
  .lesson-reader { grid-template-columns: 1fr; gap: 10px; margin-top: 0; padding-top: 15px; }
  .lesson-transcript__list { max-height: 225px; }
  p { font-size: 15px; line-height: 1.55; }
  article { grid-template-columns: 46px minmax(0, 1fr); }
  .language button, .ask { min-height: 30px; }
}
</style>
