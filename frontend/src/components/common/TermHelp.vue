<script setup lang="ts">
import { computed } from "vue";

const TERM_HELP: Record<string, string> = {
  分片上传: "大视频会被切成多个小块上传，网络中断后只需要补传失败的小块，不用从头再传。",
  原视频预览: "这里播放你刚上传的原始视频，用来确认视频是否上传正确。",
  原视频自带字幕:
    "有些视频文件内部本来就带字幕轨道，系统会尝试把它提取出来显示；如果是外挂字幕文件但没有一起上传，系统无法读取。",
  课程处理: "系统会在后台生成字幕、翻译和学习笔记。",
  "ASR 语音转文字": "AI 把视频里的声音识别成文字。",
  "字幕文件 VTT / SRT": "这是常见字幕文件格式，用来保存每句话出现的时间和文字内容。",
  全文翻译: "系统会把识别出的完整文本翻译成目标语言，方便连续阅读。",
  学习笔记: "系统会根据课程内容生成摘要、重点、术语表和问答。",
};

const props = defineProps<{
  term: string;
  content?: string;
}>();

const resolvedContent = computed(() => props.content || TERM_HELP[props.term] || "这里是该术语的简要说明。");
</script>

<template>
  <el-popover
    trigger="click"
    placement="top"
    :width="280"
    popper-class="term-help-popper"
  >
    <template #reference>
      <button class="term-help" type="button" :aria-label="`${term}说明`">?</button>
    </template>
    <div class="term-help__body">
      <strong>{{ term }}</strong>
      <p>{{ resolvedContent }}</p>
    </div>
  </el-popover>
</template>

<style scoped>
.term-help {
  display: inline-grid;
  width: 18px;
  height: 18px;
  margin-left: 6px;
  padding: 0;
  place-items: center;
  border: 1px solid #b9d2c8;
  border-radius: 50%;
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  vertical-align: middle;
}

.term-help:focus-visible {
  outline: 2px solid var(--color-brand);
  outline-offset: 2px;
}

.term-help__body {
  display: grid;
  gap: 6px;
  color: var(--color-ink-soft);
  line-height: 1.6;
}

.term-help__body strong,
.term-help__body p {
  margin: 0;
}
</style>
