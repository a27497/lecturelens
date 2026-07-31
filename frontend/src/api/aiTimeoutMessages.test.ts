import { describe, expect, it } from "vitest";
import { COURSE_CHAPTER_REQUEST_TIMEOUT_MS, toReadableCourseChapterError } from "./chapters";
import { COURSE_QA_REQUEST_TIMEOUT_MS, toReadableCourseQaError } from "./qa";
import { toUserFriendlyError } from "../utils/errorMessage";

describe("synchronous AI request timeout messages", () => {
  const timeout = { code: "ECONNABORTED" };

  it("uses the backend budget plus ten seconds and never claims background work continues", () => {
    expect(COURSE_QA_REQUEST_TIMEOUT_MS).toBe(55_000);
    expect(COURSE_CHAPTER_REQUEST_TIMEOUT_MS).toBe(70_000);
    expect(toReadableCourseQaError(timeout)).toBe("课程问答请求已超时，本次请求已结束，请缩短问题或稍后重试。");
    expect(toReadableCourseChapterError(timeout)).toBe("课程章节生成请求已超时，本次请求已结束，请稍后重试。");
    expect(toReadableCourseQaError(timeout)).not.toContain("后台");
    expect(toReadableCourseChapterError(timeout)).not.toContain("后台");
  });

  it("prefers the backend's explicit safe AI user message over a generic provider code", () => {
    expect(toUserFriendlyError({
      response: {
        status: 502,
        data: {
          code: "AI_PROVIDER_FAILED",
          message: "课程章节生成调用失败，请稍后重试。",
          data: {
            errorCode: "MODEL_NOT_FOUND",
            errorCategory: "MODEL_NOT_FOUND",
            retryable: false,
            stage: "COURSE_CHAPTER",
            userMessage: "当前 AI 模型不可用，请检查模型配置。",
          },
        },
      },
    })).toBe("当前 AI 模型不可用，请检查模型配置。");
  });
});
