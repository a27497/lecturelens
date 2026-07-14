<script setup lang="ts">
import { ref } from "vue";
import { UploadFilled } from "@element-plus/icons-vue";

const props = defineProps<{
  disabled: boolean;
}>();

const emit = defineEmits<{
  select: [file: File | null];
}>();

const dragging = ref(false);

function handleChange(event: Event) {
  const input = event.target as HTMLInputElement;
  emit("select", input.files?.[0] ?? null);
  input.value = "";
}

function handleDrop(event: DragEvent) {
  dragging.value = false;
  if (props.disabled) {
    return;
  }
  emit("select", event.dataTransfer?.files?.[0] ?? null);
}
</script>

<template>
  <section
    class="file-picker"
    :class="{ 'is-dragging': dragging, 'is-disabled': disabled }"
    aria-label="选择上传文件"
    @dragenter.prevent="dragging = true"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="handleDrop"
  >
    <el-icon class="file-picker__icon" :size="34">
      <UploadFilled />
    </el-icon>
    <div class="file-picker__body">
      <strong>选择视频文件</strong>
      <p>也可以将文件拖到这里</p>
      <div class="file-picker__details">
        <span>支持 MP4、MOV、MKV、WebM</span>
        <span>支持大文件上传和中断后继续</span>
      </div>
    </div>
    <label class="file-picker__button" :class="{ 'is-disabled': disabled }">
      <input
        :disabled="disabled"
        accept=".mp4,.mov,.mkv,.webm,video/mp4,video/quicktime,video/webm"
        type="file"
        @change="handleChange"
      />
      <span>选择文件</span>
    </label>
  </section>
</template>

<style scoped>
.file-picker {
  display: grid;
  justify-items: center;
  gap: 14px;
  min-height: 260px;
  padding: 44px 28px;
  place-content: center;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface-subtle);
  text-align: center;
  transition:
    border-color 160ms ease,
    background-color 160ms ease;
}

.file-picker.is-dragging {
  border-color: var(--color-brand);
  background: var(--color-brand-soft);
}

.file-picker.is-disabled {
  opacity: 0.65;
}

.file-picker__icon {
  color: var(--color-brand);
}

.file-picker__body {
  max-width: 540px;
}

.file-picker__body strong {
  color: var(--color-ink);
  font-size: 17px;
}

.file-picker__body p {
  margin: 8px 0 0;
  color: var(--color-ink-muted);
  font-size: 13px;
  line-height: 1.6;
}

.file-picker__details {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 14px;
  color: var(--color-ink-muted);
  font-size: 12px;
  line-height: 1.5;
}

.file-picker__details span + span::before {
  content: "·";
  margin-right: 16px;
  color: var(--color-border-strong);
}

@media (max-width: 560px) {
  .file-picker__details {
    align-items: center;
    flex-direction: column;
  }

  .file-picker__details span + span::before {
    content: none;
  }
}

.file-picker__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 18px;
  border: 1px solid var(--color-brand);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-brand-strong);
  cursor: pointer;
  font-size: 14px;
  font-weight: 680;
}

.file-picker__button:focus-within {
  outline: 2px solid var(--color-brand);
  outline-offset: 3px;
}

.file-picker__button input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.file-picker__button.is-disabled {
  border-color: var(--color-border);
  color: var(--color-ink-muted);
  cursor: not-allowed;
}
</style>
