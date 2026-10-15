<script setup lang="ts">
import { ref, watch } from "vue";
import { studyCommand } from "../../api/study";
import type { StudyApproval, StudyCommand, StudyResponse } from "../../api/study";
import { randomUuid } from "../../utils/randomUuid";

const props = defineProps<{ taskId: string; sessionId: string; runId: string; approval: StudyApproval }>();
const emit = defineEmits<{ decided: [response: StudyResponse] }>();
const text = ref("");
const editing = ref(false);
const saving = ref(false);
const message = ref("");
let pending: StudyCommand | null = null;
let generation = 0;
watch(() => [props.runId, props.approval], () => {
  generation++; pending = null; saving.value = false; editing.value = false; message.value = "";
  text.value = props.approval.preview?.explanation ?? props.approval.preview?.reason ?? "";
}, { immediate: true });
async function decide(decision: "approve" | "edit" | "reject") {
  if (saving.value || (decision === "edit" && !text.value.trim())) return;
  const current = generation;
  const edit = decision === "edit" ? text.value : undefined;
  if (!pending || pending.approval_decision !== decision || pending.approval_edit !== edit) pending = {
    operation: "DECIDE_APPROVAL", session_id: props.sessionId, run_id: props.runId,
    request_key: randomUuid(), approval_decision: decision, ...(edit !== undefined ? { approval_edit: edit } : {}),
  };
  saving.value = true; message.value = "";
  try {
    const result = await studyCommand(props.taskId, pending);
    if (generation === current) emit("decided", result);
  } catch { if (generation === current) message.value = "审批未确认，请重试同一决定或刷新查看状态。"; }
  finally { if (generation === current) saving.value = false; }
}
</script>
<template>
  <section class="study-approval" aria-label="发布审批">
    <h3>等待你的发布审批</h3>
    <p>下面是尚未发布的草稿。拒绝后本次执行结束；批准后继续执行并保存产物。</p>
    <h4 v-if="approval.preview?.title">{{ approval.preview.title }}</h4>
    <p>{{ approval.preview?.explanation ?? approval.preview?.reason }}</p>
    <p v-for="(q, index) in approval.preview?.questions" :key="index">{{ q.question }}</p>
    <p v-for="(item, index) in approval.preview?.observations" :key="index">{{ item.observation }} {{ item.next_step }}</p>
    <label v-if="editing">{{ approval.kind === 'practice' ? '修改发布说明' : '人工修改建议' }}
      <el-input v-model="text" type="textarea" :rows="4" maxlength="4000" :disabled="saving" aria-label="审批修改文字" />
      <span>修改文字会标为人工编辑；参考答案与课程引用保持原样。</span>
    </label>
    <div class="actions">
      <el-button :disabled="saving" @click="decide('approve')">批准发布</el-button>
      <el-button v-if="!editing" :disabled="saving" @click="editing = true">修改后批准</el-button>
      <el-button v-else :disabled="saving || !text.trim()" @click="decide('edit')">确认修改并批准</el-button>
      <el-button :disabled="saving" @click="decide('reject')">拒绝发布</el-button>
    </div>
    <p v-if="message" role="status">{{ message }}</p>
  </section>
</template>
<style scoped>
.study-approval { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--color-border); }
p { white-space: pre-wrap; overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
