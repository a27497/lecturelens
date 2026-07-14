<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { downloadTaskArtifactText } from "../../api/result";
import type { AnalysisTaskStatus } from "../../types/task";
import type { ResultArtifactFile } from "../../types/result";
import { getArtifactDescription, getArtifactLabel } from "../../utils/artifact";
import { formatFileSize } from "../../utils/fileSize";

const props = defineProps<{ taskId: string; status?: AnalysisTaskStatus; artifacts: ResultArtifactFile[] }>();
const downloadingKey = ref("");
const requestVersion = ref(0);
watch(() => props.taskId, () => { requestVersion.value += 1; downloadingKey.value = ""; });
function key(artifact: ResultArtifactFile) { return `${artifact.artifactType}:${artifact.language}:${artifact.fileName}`; }
async function download(artifact: ResultArtifactFile) {
  if (downloadingKey.value) return;
  const currentTaskId = props.taskId;
  const version = requestVersion.value + 1;
  requestVersion.value = version;
  downloadingKey.value = key(artifact);
  let url = "";
  try {
    const text = await downloadTaskArtifactText(currentTaskId, artifact);
    if (version !== requestVersion.value || props.taskId !== currentTaskId) return;
    url = URL.createObjectURL(new Blob([text], { type: artifact.contentType || "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = artifact.fileName || `${artifact.artifactType}-${artifact.language}`;
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
    ElMessage.success("下载已开始");
  } catch { if (version === requestVersion.value && props.taskId === currentTaskId) ElMessage.error("下载失败，请稍后重试"); }
  finally {
    if (url) URL.revokeObjectURL(url);
    if (version === requestVersion.value && props.taskId === currentTaskId) downloadingKey.value = "";
  }
}
function emptyText() { return props.status === "FAILED" ? "处理失败，暂无下载文件" : props.status === "CANCELED" ? "处理已取消，暂无下载文件" : "下载文件生成中"; }
</script>

<template>
  <section class="workspace-panel files-panel" aria-labelledby="files-title">
    <header><h2 id="files-title">下载</h2><p>保存字幕、学习资料或结构化结果。</p></header>
    <el-empty v-if="artifacts.length === 0" :description="emptyText()" />
    <div v-else class="file-list">
      <article v-for="artifact in artifacts" :key="key(artifact)" class="file-row">
        <div><strong>{{ getArtifactLabel(artifact.artifactType) }}</strong><span>{{ getArtifactDescription(artifact.artifactType) }}</span></div>
        <span>{{ artifact.language }}</span><span>{{ formatFileSize(artifact.sizeBytes) }}</span>
        <el-button size="small" type="primary" plain :loading="downloadingKey === key(artifact)" @click="download(artifact)">下载</el-button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p { margin: 0; } header p { color: var(--color-ink-soft); }
.file-list { display: grid; border-top: 1px solid var(--color-border); }.file-row { display: grid; grid-template-columns: minmax(0,1fr) 100px 90px auto; align-items: center; gap: 18px; padding: 16px 0; border-bottom: 1px solid var(--color-border); }.file-row > div { display: grid; gap: 5px; min-width: 0; }.file-row span { color: var(--color-ink-soft); font-size: 13px; overflow-wrap: anywhere; }
@media (max-width: 680px) { .file-row { grid-template-columns: 1fr auto; }.file-row > div { grid-column: 1 / -1; } }
</style>
