<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { choiceReview, type ChoiceReview, type ChoiceReviewItem } from '../../api/study';
import { mayHaveLostCourseAccess } from '../../api/courseAccess';
import { formatMillisRange } from '../../utils/time';
import type { EvidenceSeekContext } from './evidenceSeekGuard';

const props = defineProps<{ taskId: string; revision: number; refreshKey: number }>();
const emit = defineEmits<{ open: [item: ChoiceReviewItem]; seek: [milliseconds: number, context: EvidenceSeekContext]; accessFailure: [] }>();
const expanded = ref(false);
const data = ref<ChoiceReview | null>(null);
const loading = ref(false);
const error = ref('');
const offset = ref(0);
let generation = 0;
watch(() => [props.taskId, props.revision], () => {
  generation++; data.value = null; error.value = ''; loading.value = false; offset.value = 0;
  if (expanded.value) void read();
});
watch(() => props.refreshKey, () => { if (expanded.value) void read(); else data.value = null; });
onBeforeUnmount(() => { generation++; });
async function read(after = 0) {
  const current = ++generation;
  loading.value = true; error.value = ''; data.value = null;
  try {
    const response = await choiceReview(props.taskId, after);
    if (current !== generation) return;
    if (response.revision !== props.revision) throw new Error('Revision changed');
    data.value = response; offset.value = after;
  } catch (failure) {
    if (current !== generation) return;
    error.value = '答错记录暂时无法读取，请重新打开课程或重试。';
    if (mayHaveLostCourseAccess(failure)) emit('accessFailure');
  } finally { if (current === generation) loading.value = false; }
}
function toggle() {
  expanded.value = !expanded.value;
  if (expanded.value) void read();
}
function optionText(item: ChoiceReviewItem, id?: string) {
  return item.question.options?.find(option => option.id === id)?.text ?? '';
}
</script>
<template>
  <section class="choice-review" aria-label="答错待回看">
    <el-button :aria-expanded="expanded" @click="toggle">{{ expanded ? '收起答错待回看' : '答错待回看' }}</el-button>
    <template v-if="expanded">
      <p>本课程当前版本 · 跨学习会话回看，每题仅统计最新已提交版本。</p>
      <p class="boundary">仅统计已提交的选择题程序判分结果，不是掌握程度。空答、开放题反馈和闪卡自评不计入。</p>
      <p v-if="loading" role="status">正在读取已保存判分…</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <template v-if="data">
        <p class="judgment-counts">已提交程序判分：正确 {{ data.correct_count }} · 错误 {{ data.wrong_count }}</p>
        <p v-if="!data.wrong_count" role="status">暂无答错待回看的选择题。这仅表示最新已提交版本中没有错误记录。</p>
        <p v-else-if="!data.items.length" role="status">记录已变化，请刷新列表查看最新结果。</p>
        <article v-for="item in data.items" :key="item.attempt.attempt_id" class="review-item">
          <h3>第 {{ item.question_index + 1 }} 题 · {{ item.question.question }}</h3>
          <ul><li v-for="option in item.question.options" :key="option.id">{{ option.id }}. {{ option.text }}</li></ul>
          <p>已保存第 {{ item.attempt.version }} 版 · 选择：{{ item.attempt.selected_option_id }}. {{ optionText(item, item.attempt.selected_option_id) }}</p>
          <p>程序判分：错误 · 正确选项：{{ item.attempt.choice_result?.correct_option_id }}. {{ optionText(item, item.attempt.choice_result?.correct_option_id) }}</p>
          <el-button @click="emit('open', item)">打开原题与作答</el-button>
          <div v-for="citation in item.attempt.choice_result?.citations" :key="citation.evidence_id">
            <blockquote>{{ citation.text }}</blockquote>
            <el-button @click="emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision })">{{ formatMillisRange(citation.start_ms, citation.end_ms) }} · 回看课程原文</el-button>
          </div>
        </article>
        <div class="review-pages"><el-button v-if="offset" :disabled="loading" @click="read(Math.max(0, offset - 20))">上一页答错记录</el-button><el-button v-if="data.next_after !== null" :disabled="loading" @click="read(data.next_after)">下一页答错记录</el-button></div>
        <p v-if="data.wrong_count">每页最多 20 题，按最近提交排序；记录变化后请刷新。</p>
      </template>
      <el-button :loading="loading" @click="read()">刷新答错记录</el-button>
    </template>
  </section>
</template>
<style scoped>
.choice-review { margin: 16px 0; padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
p,li,blockquote { line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.boundary { color: var(--color-text-secondary); font-size: 13px; }
.review-item { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--color-border); }
h3 { font-size: 15px; } blockquote { margin: 12px 0; padding-left: 12px; border-left: 3px solid var(--color-border); }
.review-pages { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
</style>
