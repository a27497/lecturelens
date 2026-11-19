import type { TaskEventPayload } from "../../types/task";
import { formatApiTimestamp } from "../../utils/time";

export type CourseWorkspace = "tutor" | "notes" | "flashcards" | "overview" | "content" | "study" | "qa" | "agent" | "files" | "technical";

export const WORKSPACE_ITEMS: Array<{ value: CourseWorkspace; label: string }> = [
  { value: "tutor", label: "Tutor 对话" },
  { value: "notes", label: "个人笔记" },
  { value: "agent", label: "学习助手" },
  { value: "flashcards", label: "闪卡复习" },
  { value: "overview", label: "概览" },
  { value: "content", label: "课程内容" },
  { value: "study", label: "学习资料" },
  { value: "qa", label: "课程问答" },
  { value: "files", label: "下载" },
  { value: "technical", label: "处理详情" },
];

export function workspaceLabel(value: CourseWorkspace, compact = true): string {
  if (compact && value === "content") return "课程材料";
  if (compact && value === "agent") return "解释与练习";
  return WORKSPACE_ITEMS.find(item => item.value === value)?.label ?? value;
}

/** Mirrors the backend rule: SUCCEEDED, or RUNNING once this run's subtitles opened learning. */
export function courseLearnable(status?: string | null, learningReady?: boolean | null): boolean {
  return status === "SUCCEEDED" || (status === "RUNNING" && learningReady === true);
}

export function courseStageText(stage: string, status?: TaskEventPayload["status"]): string {
  if (status === "CANCELED") {
    return "已取消";
  }
  if (status === "SUCCEEDED") {
    return "已完成";
  }
  if (status === "FAILED") {
    if (stage === "GENERATE_ARTIFACTS" || stage === "WRITE_AI_CALL_RECORD") {
      return "生成下载文件失败";
    }
    return "处理失败";
  }
  switch (stage) {
    case "VALIDATE_TASK":
    case "RESOLVE_UPLOADED_SOURCE":
      return "正在读取视频";
    case "EXTRACT_AUDIO":
      return "正在提取音频";
    case "TRANSCRIBE":
    case "TRANSCRIBING":
    case "ASR":
    case "PERSIST_SUBTITLES":
      return "正在生成字幕";
    case "TRANSLATE":
    case "TRANSLATE_SUBTITLES":
    case "TRANSLATING":
      return "正在生成翻译";
    case "GENERATE_LEARNING_PACKAGE":
    case "EXTRACT_KEYFRAMES":
    case "ANALYZE_KEYFRAMES":
    case "OCR_KEYFRAMES":
      return "正在生成学习资料";
    case "GENERATE_ARTIFACTS":
    case "WRITE_AI_CALL_RECORD":
      return "正在生成下载文件";
    case "DONE":
      return "已完成";
    case "FAILED":
      return "处理失败";
    default:
      return stage ? "处理中" : "等待处理";
  }
}

export function readableTaskError(message: string): string {
  if (!message) return "";
  if (message.includes("audio file exceeds configured limit") || message.includes("SiliconFlow ASR configuration is invalid")) {
    return "字幕生成失败：音频文件过大，当前配置暂不支持这么长的视频。";
  }
  if (/SiliconFlow ASR (request failed with HTTP (408|429|500|502|503|504)|request timed out|network call failed)/.test(message)) {
    return "字幕服务暂时不可用，请稍后重新处理。";
  }
  if (message.includes("non-Chinese text") || message.includes("中文全文生成失败") || message.includes("没有返回有效中文译文")) {
    return "中文翻译生成失败，请稍后重新处理。";
  }
  if (message.includes("Markdown glossary") || message.includes("JSON artifact content is invalid")) {
    return "下载文件生成失败，部分术语字段缺失。";
  }
  return message;
}

export function formatWorkspaceTime(value: string | null | undefined): string {
  return formatApiTimestamp(value);
}

export function connectionText(status: string): string {
  switch (status) {
    case "connecting": return "连接中";
    case "connected": return "实时更新中";
    case "reconnecting": return "重连中";
    case "closed": return "已结束";
    case "error": return "连接异常";
    default: return "未连接";
  }
}
