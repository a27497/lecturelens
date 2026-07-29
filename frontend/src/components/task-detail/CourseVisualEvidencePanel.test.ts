import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import CourseVisualEvidencePanel from "./CourseVisualEvidencePanel.vue";
import { downloadTaskKeyframeImage } from "../../api/result";
import type { ResultKeyframe, ResultVideoSegment } from "../../types/result";

vi.mock("../../api/result", () => ({
  downloadTaskKeyframeImage: vi.fn(),
  isTaskResultAuthError: (error: unknown) => {
    const status = (error as { response?: { status?: number } })?.response?.status;
    return status === 401 || status === 403;
  },
  toReadableKeyframeImageError: () => "画面加载失败，请重试",
}));

const downloadImage = vi.mocked(downloadTaskKeyframeImage);
let createObjectUrl: ReturnType<typeof vi.spyOn>;
let revokeObjectUrl: ReturnType<typeof vi.spyOn>;

beforeAll(() => {
  createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:keyframe-1");
  revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
});

afterAll(() => {
  createObjectUrl.mockRestore();
  revokeObjectUrl.mockRestore();
});

beforeEach(() => {
  downloadImage.mockReset();
  createObjectUrl.mockClear();
  revokeObjectUrl.mockClear();
});

describe("CourseVisualEvidencePanel", () => {
  it("loads an authenticated image blob and renders visual evidence metadata", async () => {
    downloadImage.mockResolvedValue(new Blob(["image"], { type: "image/jpeg" }));
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: {
        taskId: "task_1",
        keyframes: [keyframe()],
        videoSegments: [videoSegment()],
      },
    });

    await flushPromises();

    expect(downloadImage).toHaveBeenCalledWith("task_1", 9, expect.any(AbortSignal));
    expect(wrapper.get("img").attributes("src")).toBe("blob:keyframe-1");
    expect(wrapper.text()).toContain("PPT 上的三个步骤");
    expect(wrapper.text()).toContain("课程架构图包含三个模块");
    expect(wrapper.text()).toContain("OCR");
    expect(wrapper.text()).toContain("视觉分析");
    expect(wrapper.text()).toContain("ASR+画面");

    await wrapper.get('[data-testid="seek-frame-9"]').trigger("click");
    await wrapper.get('[data-testid="image-frame-9"]').trigger("click");
    expect(wrapper.emitted("seek")).toEqual([[12_345], [12_345]]);

    wrapper.unmount();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:keyframe-1");
  });

  it("shows a clear image failure and retries successfully", async () => {
    downloadImage
      .mockRejectedValueOnce(new Error("image request failed"))
      .mockResolvedValueOnce(new Blob(["image"], { type: "image/jpeg" }));
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: {
        taskId: "task_1",
        keyframes: [keyframe()],
        videoSegments: [],
      },
    });

    await flushPromises();
    expect(wrapper.text()).toContain("画面加载失败，请重试");

    await wrapper.get('[data-testid="retry-frame-9"]').trigger("click");
    await flushPromises();

    expect(downloadImage).toHaveBeenCalledTimes(2);
    expect(wrapper.find("img").exists()).toBe(true);
    wrapper.unmount();
  });

  it("loads one page at a time and revokes URLs when the page changes", async () => {
    downloadImage.mockResolvedValue(new Blob(["image"], { type: "image/jpeg" }));
    const keyframes = Array.from({ length: 9 }, (_, index) => ({
      ...keyframe(),
      frameId: index + 1,
      timestampMillis: index * 10_000,
      timeText: `00:${String(index * 10).padStart(2, "0")}.000`,
    }));
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: { taskId: "task_1", keyframes, videoSegments: [] },
    });

    await flushPromises();
    expect(downloadImage).toHaveBeenCalledTimes(8);

    const nextPage = wrapper.findAll("button").find((button) => button.text() === "下一页");
    expect(nextPage).toBeDefined();
    await nextPage!.trigger("click");
    await flushPromises();

    expect(downloadImage).toHaveBeenCalledTimes(9);
    expect(revokeObjectUrl).toHaveBeenCalledTimes(8);
    expect(wrapper.text()).toContain("第 2 / 2 页");
    wrapper.unmount();
  });

  it("aborts stale image requests on task switch and ignores their response", async () => {
    let resolveOldRequest!: (blob: Blob) => void;
    downloadImage
      .mockImplementationOnce((_taskId, _frameId, signal) => new Promise((resolve, reject) => {
        resolveOldRequest = resolve;
        signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      }))
      .mockResolvedValueOnce(new Blob(["new-image"], { type: "image/jpeg" }));
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: { taskId: "task_old", keyframes: [keyframe()], videoSegments: [] },
    });
    await Promise.resolve();
    const oldSignal = downloadImage.mock.calls[0]?.[2];

    await wrapper.setProps({ taskId: "task_new" });
    await flushPromises();
    resolveOldRequest(new Blob(["old-image"], { type: "image/jpeg" }));
    await flushPromises();

    expect(oldSignal?.aborted).toBe(true);
    expect(downloadImage.mock.calls.at(-1)?.[0]).toBe("task_new");
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("aborts pending requests on unmount", async () => {
    downloadImage.mockImplementation((_taskId, _frameId, signal) => new Promise((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: { taskId: "task_1", keyframes: [keyframe()], videoSegments: [] },
    });
    await Promise.resolve();
    const signal = downloadImage.mock.calls[0]?.[2];

    wrapper.unmount();

    expect(signal?.aborted).toBe(true);
  });

  it("does not offer a retry for authorization failures", async () => {
    downloadImage.mockRejectedValue({ response: { status: 403 } });
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: { taskId: "task_1", keyframes: [keyframe()], videoSegments: [] },
    });
    await flushPromises();

    expect(wrapper.find('[data-testid="retry-frame-9"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("renders only a bounded OCR preview", async () => {
    downloadImage.mockResolvedValue(new Blob(["image"], { type: "image/jpeg" }));
    const longText = "x".repeat(600);
    const frame = keyframe();
    frame.ocr = { ...frame.ocr!, text: longText };
    const wrapper = mount(CourseVisualEvidencePanel, {
      props: { taskId: "task_1", keyframes: [frame], videoSegments: [] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain(`${"x".repeat(480)}…`);
    expect(wrapper.text()).not.toContain("x".repeat(481));
    wrapper.unmount();
  });
});

function keyframe(): ResultKeyframe {
  return {
    frameId: 9,
    timestampMillis: 12_345,
    timeText: "00:12.345",
    imageUrl: "/api/tasks/task_1/keyframes/9/image",
    changeScore: 0.42,
    selectReason: "SCENE_CHANGE",
    createdAt: "2026-07-29T10:00:00",
    ocr: {
      status: "SUCCEEDED",
      text: "PPT 上的三个步骤",
      provider: "tesseract",
      languageHint: "chi_sim+eng",
      confidence: 0.91,
      truncated: false,
      message: "",
    },
    visualAnalysis: {
      status: "SUCCEEDED",
      screenType: "PPT",
      summary: "课程架构图包含三个模块",
      detectedElements: ["标题", "架构图"],
      provider: "mock-vision",
      model: "mock-model",
      message: "",
    },
  };
}

function videoSegment(): ResultVideoSegment {
  return {
    segmentId: 4,
    segmentIndex: 0,
    startMillis: 0,
    endMillis: 60_000,
    timeText: "00:00:00 - 00:01:00",
    asrText: "老师讲解课程架构",
    ocrText: "PPT 上的三个步骤",
    visualSummary: "课程架构图",
    fusedSummary: "老师结合架构图进行讲解",
    keywords: ["架构"],
    evidence: {
      subtitleSegmentIds: [1],
      keyframeIds: [9],
      ocrIds: [2],
      visualAnalysisIds: [3],
      counts: { asr: 1, visual: 1 },
    },
    status: "SUCCEEDED",
    confidence: 0.88,
  };
}
