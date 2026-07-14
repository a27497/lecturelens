export function getArtifactLabel(artifactType: string): string {
  switch (normalizeArtifactType(artifactType)) {
    case "SRT":
      return "SRT 字幕";
    case "VTT":
      return "VTT 字幕";
    case "MARKDOWN":
      return "Markdown 学习笔记";
    case "JSON":
      return "JSON 结果";
    default:
      return artifactType || "导出文件";
  }
}

export function getArtifactDescription(artifactType: string): string {
  switch (normalizeArtifactType(artifactType)) {
    case "SRT":
      return "常见字幕格式，可导入播放器或剪辑软件。";
    case "VTT":
      return "网页播放器常用字幕格式。";
    case "MARKDOWN":
      return "适合阅读和整理的学习笔记。";
    case "JSON":
      return "适合开发调试或二次处理的数据格式。";
    default:
      return "系统生成的课程分析导出文件。";
  }
}

export function normalizeArtifactType(artifactType: string): string {
  return artifactType.trim().toUpperCase();
}
