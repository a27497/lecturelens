import type { TaskEventPayload } from "../../types/task";

export type CourseWorkspace = "overview" | "content" | "study" | "qa" | "files" | "technical";

export function courseStageText(stage: string, status?: TaskEventPayload["status"]): string {
  if (status === "FAILED" && (stage === "GENERATE_ARTIFACTS" || stage === "WRITE_AI_CALL_RECORD")) {
    return "生成下载文件失败";
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
  if (!value) return "暂无";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
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
