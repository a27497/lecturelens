<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchCourseChapters, generateCourseChapters, toReadableCourseChapterError } from "../api/chapters";
import type { CourseChapterResponse, CourseChapterUsage } from "../types/chapter";
import { formatMillisRange } from "../utils/time";

const props = defineProps<{
  taskId: string;
}>();

const emit = defineEmits<{
  seek: [startTimeMillis: number];
}>();

const chapters = ref<CourseChapterResponse[]>([]);
const loading = ref(false);
const generating = ref(false);
const errorMessage = ref("");
const requestVersion = ref(0);

const hasChapters = computed(() => chapters.value.length > 0);
const chapterUsage = computed<CourseChapterUsage | null>(
  () => chapters.value.find((chapter) => chapter.usage !== null)?.usage ?? null,
);

watch(() => props.taskId, () => {
  requestVersion.value += 1;
  chapters.value = [];
  loading.value = false;
  generating.value = false;
  errorMessage.value = "";
  void loadChapters();
}, { immediate: true });

async function loadChapters() {
  const currentTaskId = props.taskId;
  if (!currentTaskId || loading.value || generating.value) return;
  const version = requestVersion.value + 1;
  requestVersion.value = version;
  loading.value = true;
  errorMessage.value = "";
  try {
    const nextChapters = await fetchCourseChapters(currentTaskId);
    if (version !== requestVersion.value || props.taskId !== currentTaskId) return;
    chapters.value = nextChapters;
  } catch (error) {
    if (version === requestVersion.value && props.taskId === currentTaskId) errorMessage.value = toReadableCourseChapterError(error);
  } finally {
    if (version === requestVersion.value && props.taskId === currentTaskId) loading.value = false;
  }
}

async function generateChapters() {
  const currentTaskId = props.taskId;
  if (!currentTaskId || generating.value || loading.value) return;
  const version = requestVersion.value + 1;
  requestVersion.value = version;
  generating.value = true;
  errorMessage.value = "";
  try {
    const nextChapters = await generateCourseChapters(currentTaskId);
    if (version !== requestVersion.value || props.taskId !== currentTaskId) return;
    chapters.value = nextChapters;
  } catch (error) {
    if (version === requestVersion.value && props.taskId === currentTaskId) errorMessage.value = toReadableCourseChapterError(error);
  } finally {
    if (version === requestVersion.value && props.taskId === currentTaskId) generating.value = false;
  }
}

function chapterTimeText(chapter: CourseChapterResponse): string {
  return chapter.timeText || formatMillisRange(chapter.startTimeMillis, chapter.endTimeMillis);
}

function chapterKey(chapter: CourseChapterResponse): string {
  return `${chapter.id ?? chapter.chapterIndex}-${chapter.startTimeMillis}-${chapter.endTimeMillis}`;
}

function seekToChapter(chapter: CourseChapterResponse) {
  emit("seek", Math.max(0, chapter.startTimeMillis || 0));
}

function hasUsageNumber(value: number | null): boolean {
  return value !== null && value !== undefined;
}
</script>

<template>
  <section class="course-chapters-panel" aria-label="课程章节">
    <div class="course-chapters-panel__header">
      <div>
        <h3>课程章节</h3>
        <p class="result-help">根据课程内容生成章节。章节只会在你点击按钮后生成。</p>
      </div>
      <div class="course-chapters-panel__actions">
        <el-button :loading="loading" :disabled="generating" @click="loadChapters">刷新</el-button>
        <el-button type="primary" :loading="generating" :disabled="loading" @click="generateChapters">
          {{ hasChapters ? "重新生成" : "生成课程章节" }}
        </el-button>
      </div>
    </div>

    <el-alert v-if="errorMessage" :closable="false" :title="errorMessage" type="warning" show-icon />

    <el-skeleton v-if="loading && !hasChapters" :rows="4" animated />
    <el-empty v-else-if="!hasChapters" description="尚未生成课程章节" />

    <div v-else class="course-chapter-list">
      <details v-if="chapterUsage" :key="`usage-${taskId}`" class="course-chapters-panel__details">
        <summary>章节生成详情</summary>
        <div class="course-chapters-panel__usage">
          <span v-if="chapterUsage.provider">{{ chapterUsage.provider }}</span>
          <span v-if="chapterUsage.model">{{ chapterUsage.model }}</span>
          <span v-if="hasUsageNumber(chapterUsage.totalTokens)">{{ chapterUsage.totalTokens }} tokens</span>
          <span v-if="hasUsageNumber(chapterUsage.durationMillis)">{{ chapterUsage.durationMillis }} ms</span>
        </div>
      </details>
      <article
        v-for="chapter in chapters"
        :key="`${taskId}-${chapterKey(chapter)}`"
        class="course-chapter-item"
      >
        <div class="course-chapter-item__time">{{ chapterTimeText(chapter) }}</div>
        <div class="course-chapter-item__body">
          <div class="course-chapter-item__title-row">
            <h4>{{ chapter.title }}</h4>
            <el-tag size="small" effect="plain">第 {{ chapter.chapterIndex + 1 }} 章</el-tag>
          </div>
          <p>{{ chapter.summary }}</p>
          <div v-if="chapter.keywords.length > 0" class="course-chapter-item__keywords">
            <el-tag v-for="keyword in chapter.keywords" :key="keyword" size="small">
              {{ keyword }}
            </el-tag>
          </div>
          <div v-if="chapter.evidence.length > 0" class="course-chapter-item__evidence">
            <span>证据 {{ chapter.evidence.length }} 段</span>
          </div>
          <el-button class="course-chapter-item__seek" size="small" plain @click="seekToChapter(chapter)">
            跳到视频
          </el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.course-chapters-panel {
  display: grid;
  gap: 14px;
  min-width: 0;
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.course-chapters-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.course-chapters-panel__header h3,
.course-chapter-item h4 {
  margin: 0;
  color: var(--color-ink);
}

.course-chapters-panel__actions,
.course-chapters-panel__usage,
.course-chapter-item__title-row,
.course-chapter-item__keywords,
.course-chapter-item__evidence {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.course-chapter-list {
  display: grid;
  gap: 10px;
}

.course-chapters-panel__usage {
  margin-top: 8px;
  color: var(--color-ink-soft);
  font-size: 12px;
}

.course-chapters-panel__details summary {
  width: fit-content;
  color: var(--color-ink-soft);
  font-size: 13px;
  cursor: pointer;
}

.course-chapter-item {
  display: grid;
  grid-template-columns: minmax(120px, 170px) minmax(0, 1fr);
  gap: 14px;
  padding: 14px;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
  transition: border-color 0.16s ease, background 0.16s ease;
}

.course-chapter-item:hover {
  background: var(--color-canvas);
}

.course-chapter-item__time {
  color: var(--color-brand);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  font-weight: 700;
}

.course-chapter-item__body {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.course-chapter-item__title-row {
  justify-content: space-between;
}

.course-chapter-item p {
  margin: 0;
  color: var(--color-ink-soft);
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.course-chapter-item__evidence {
  color: var(--color-ink-soft);
  font-size: 12px;
}

.course-chapter-item__seek {
  width: fit-content;
}

@media (max-width: 720px) {
  .course-chapters-panel__header,
  .course-chapter-item {
    grid-template-columns: 1fr;
  }

  .course-chapters-panel__header {
    display: grid;
  }
}
</style>
