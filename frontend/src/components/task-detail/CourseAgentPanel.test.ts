import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CourseAgentPanel from "./CourseAgentPanel.vue";
import { getEvidenceIndexStatus } from "../../api/qa";
import { studyCommand, studyEvents, studyStatus } from "../../api/study";
import type { StudyArtifact, StudyRun } from "../../api/study";

vi.mock("../../api/qa", () => ({ getEvidenceIndexStatus: vi.fn() }));
vi.mock("../../api/study", () => ({ studyStatus: vi.fn(), studyCommand: vi.fn(), studyEvents: vi.fn() }));
const run: StudyRun = { run_id: "run", session_id: "session", goal: "解释并出题", status: "succeeded", model_mode: "real", model_calls: 3, tool_calls: 3, error_code: null };
const artifact: StudyArtifact = { artifact_id: "artifact", title: "停止条件", explanation: "课程中描述停止条件让算法可以终止。", evidence_ids: ["e1"], questions: [{ question: "为什么需要停止条件？", evidence_ids: ["e1"] }, { question: "举一个有限执行的例子？", evidence_ids: ["e1"] }], citations: [{ evidence_id: "e1", text: "The algorithm stops.", start_ms: 1234, end_ms: 2345, source_type: "SUBTITLE" }], revision: 1, mode: "real" };
const stubs = {
  "el-input": { props: ["modelValue"], emits: ["update:modelValue"], template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
  "el-button": { props: ["disabled"], template: `<button :disabled="disabled"><slot /></button>` },
  "el-alert": { props: ["title"], template: `<p role="alert">{{ title }}</p>` },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(studyCommand).mockResolvedValue({ sessions: [], runs: [] });
  vi.mocked(studyStatus).mockResolvedValue({ enabled: true, revision: 1 });
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ status: "READY" } as never);
});

it("restores a completed run, keeps answers private and preserves citation seek", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "ANSWERS") return { questions: [{ question: "why", evidence_ids: ["e1"], answer: "PRIVATE ANSWER", rubric: "matching source" }] };
    return { run, artifact };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.text()).toContain("停止条件");
  expect(wrapper.text()).not.toContain("PRIVATE ANSWER");
  expect(vi.mocked(studyCommand).mock.calls.some(call => call[1].operation === "ANSWERS")).toBe(false);
  await wrapper.findAll("button").find(button => button.text().includes("跳到视频"))!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[1234, { evidenceId: "e1", revision: 1 }]]);
  await wrapper.findAll("button").find(button => button.text().includes("查看参考答案"))!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("PRIVATE ANSWER");
  wrapper.unmount();
});

it("restores an active execution and cancels it immediately", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run: { ...run, status: command.operation === "CANCEL" ? "cancelled" : "running" }, artifact: null };
  });
  vi.mocked(studyEvents).mockImplementation(() => new Promise(() => {}));
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(studyEvents).toHaveBeenCalledWith("task", "session", "run", 0, expect.any(AbortSignal), expect.any(Function));
  await wrapper.findAll("button").find(button => button.text() === "取消本次执行")!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("已取消");
  expect(wrapper.findAll("button").some(button => button.text() === "取消本次执行")).toBe(false);
  wrapper.unmount();
});

it("ignores a previous course's late session response", async () => {
  let resolveOld!: (value: { sessions: { session_id: string; revision: number }[] }) => void;
  vi.mocked(studyCommand).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValue({ sessions: [] });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "old" }, global: { stubs } });
  await flushPromises();
  await wrapper.setProps({ taskId: "new" });
  await flushPromises();
  resolveOld({ sessions: [{ session_id: "old-session", revision: 1 }] });
  await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls.some(call => call[1].session_id === "old-session")).toBe(false);
  wrapper.unmount();
});

it("does not restore an older artifact when starting a new goal fails", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "START") throw new Error("transport unavailable");
    return { run: { ...run, request_key: "old-key" }, artifact };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.find(".study-artifact").exists()).toBe(true);
  await wrapper.findAll("textarea")[0]!.setValue("新的学习目标");
  await wrapper.findAll("button").find(button => button.text() === "解释并出题")!.trigger("click");
  await flushPromises();
  expect(wrapper.find(".study-artifact").exists()).toBe(false);
  wrapper.unmount();
});


it("ignores late answers from a completed run after a new run starts", async () => {
  let resolveAnswers!: (value: { questions: { question: string; evidence_ids: string[]; answer: string }[] }) => void;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "ANSWERS") return new Promise(resolve => { resolveAnswers = resolve; });
    if (command.operation === "START") return { run: { ...run, run_id: "new-run" }, artifact: { ...artifact, title: "新练习" } };
    return { run, artifact };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text().includes("查看参考答案"))!.trigger("click");
  await wrapper.findAll("textarea")[0]!.setValue("新的学习目标");
  await wrapper.findAll("button").find(button => button.text() === "解释并出题")!.trigger("click");
  await flushPromises();
  resolveAnswers({ questions: [{ question: "old", evidence_ids: ["e1"], answer: "OLD PRIVATE ANSWER" }] });
  await flushPromises();
  expect(wrapper.text()).toContain("新练习");
  expect(wrapper.text()).not.toContain("OLD PRIVATE ANSWER");
  wrapper.unmount();
});


it("shows insufficient evidence without empty practice or answer controls", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run, artifact: { ...artifact, kind: "insufficient_evidence", explanation: "本段课程没有涉及该主题。", questions: [], citations: [] } };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.text()).toContain("本段课程没有涉及该主题。");
  expect(wrapper.findAll("h3").some(heading => heading.text() === "两道自测题")).toBe(false);
  expect(wrapper.findAll("button").some(button => button.text().includes("查看参考答案"))).toBe(false);
  wrapper.unmount();
});

it("offers course reading when disabled without requiring the retrieval service", async () => {
  vi.mocked(studyStatus).mockResolvedValue({ enabled: false, revision: 1 });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(getEvidenceIndexStatus).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("学习助手尚未启用");
  await wrapper.findAll("button").find(button => button.text() === "阅读课程内容")!.trigger("click");
  expect(wrapper.emitted("navigate")).toEqual([["content"]]);
  wrapper.unmount();
});

it("distinguishes a status failure from disabled and allows reconnection", async () => {
  vi.mocked(studyStatus).mockRejectedValueOnce(new Error("offline"));
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.text()).not.toContain("学习助手尚未启用");
  await wrapper.findAll("button").find(button => button.text() === "重新连接")!.trigger("click");
  await flushPromises();
  expect(wrapper.findAll("textarea").length).toBeGreaterThan(0);
  wrapper.unmount();
});

it("keeps learning unavailable while evidence is being prepared and can refresh", async () => {
  vi.mocked(getEvidenceIndexStatus).mockResolvedValueOnce({ status: "INDEXING" } as Awaited<ReturnType<typeof getEvidenceIndexStatus>>);
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.findAll("textarea")[0]!.setValue("解释停止条件");
  expect(wrapper.findAll("button").find(button => button.text() === "解释并出题")!.attributes("disabled")).toBeDefined();
  await wrapper.findAll("button").find(button => button.text() === "刷新状态")!.trigger("click");
  await flushPromises();
  expect(wrapper.findAll("button").find(button => button.text() === "解释并出题")!.attributes("disabled")).toBeUndefined();
  wrapper.unmount();
});


it("shows preparation before querying the study gateway for a processing course", async () => {
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task", status: "RUNNING" }, global: { stubs } });
  await flushPromises();
  expect(studyStatus).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("课程内容尚未处理完成");
  await wrapper.find("button").trigger("click");
  expect(wrapper.emitted("navigate")).toEqual([["overview"]]);
  await wrapper.setProps({ status: "SUCCEEDED" }); await flushPromises();
  expect(studyStatus).toHaveBeenCalledWith("task");
  wrapper.unmount();
});

it("opens a saved older run from learning history", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "RUNS") return { runs: [{ run_id: "older", goal: "之前的学习目标", status: "succeeded", created_at: "2026-09-20" }] };
    return { run: { ...run, run_id: command.run_id ?? "latest" }, artifact: { ...artifact, title: command.run_id === "older" ? "以前的练习" : "当前练习" } };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text() === "之前的学习目标")!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("以前的练习");
  expect(studyCommand).toHaveBeenCalledWith("task", expect.objectContaining({ operation: "READ", run_id: "older" }));
  wrapper.unmount();
});

it("restores the frozen approval choice and waiting draft after reload", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run: { ...run, status: "awaiting_approval", approval_required: true }, artifact: null,
      approval: { kind: "practice", decision: null, preview: { title: "unpublished draft", explanation: "preview only" } } };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect((wrapper.find('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true);
  expect(wrapper.text()).toContain("等待你的发布审批");
  expect(wrapper.find(".study-artifact").exists()).toBe(false);
  expect(studyEvents).not.toHaveBeenCalled();
  wrapper.unmount();
});

it("uses the CREATE_SESSION source revision rather than the artifact edit revision", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [] };
    if (command.operation === "CREATE_SESSION") return { session_id: "session", revision: 2 };
    if (command.operation === "START") return { run, artifact };
    return {};
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.get("textarea").setValue("Explain the new course source");
  await wrapper.findAll("button").find(button => button.text() === "解释并出题")!.trigger("click");
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text().includes("跳到视频"))!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[1234, { evidenceId: "e1", revision: 2 }]]);
  wrapper.unmount();
});

it("freezes the selected scope before session creation and reports the restored Run scope", async () => {
  const chosen = { version: 1 as const, kind: 'segments' as const, policy: 'strict' as const, revision: 1, evidence_ids: ['e1'] };
  let finishSession!: (value: { session_id: string; revision: number }) => void;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'CREATE_SESSION') return new Promise(resolve => { finishSession = resolve; });
    if (command.operation === 'START') return { run: { ...run, learning_scope: command.learning_scope }, artifact };
    return { sessions: [], runs: [] };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task', learningScope: chosen }, global: { stubs } });
  await flushPromises(); await wrapper.get('textarea').setValue('Selected stopping condition');
  await wrapper.findAll('button').find(b => b.text() === '解释并出题')!.trigger('click'); await flushPromises();
  await wrapper.setProps({ learningScope: { ...chosen, policy: 'course' } });
  finishSession({ session_id: 'session', revision: 1 }); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls.find(c => c[1].operation === 'START')![1].learning_scope).toEqual(chosen);
  expect(wrapper.emitted('frozenScope')!.at(-1)).toEqual([chosen]); wrapper.unmount();
});

it("keeps each question draft when navigating and only emits page navigation metadata", async () => {
  const attempt = { attempt_id: "a1", artifact_id: "artifact", question_index: 0, version: 1, answer_text: "Saved v1", created_at: "2026-10-01T00:00:00Z" };
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run, artifact, attempts: [attempt] };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  const fields = wrapper.findAll(".practice-answer textarea");
  await fields[0]!.setValue("UNSAVED question one");
  await wrapper.findAll(".question-nav button")[1]!.trigger("click");
  await fields[1]!.setValue("UNSAVED question two");
  await wrapper.findAll(".question-nav button")[0]!.trigger("click");
  expect((fields[0]!.element as HTMLTextAreaElement).value).toBe("UNSAVED question one");
  expect((fields[1]!.element as HTMLTextAreaElement).value).toBe("UNSAVED question two");
  expect(wrapper.findAll(".question-nav button")[0]!.text()).toContain("有未保存修改");
  expect(wrapper.emitted("position")!.at(-1)).toEqual([{ goal: run.goal, question: artifact.questions[0]!.question, questionIndex: 0, totalQuestions: 2, savedQuestions: 1 }]);
  expect(JSON.stringify(wrapper.emitted("position"))).not.toContain("UNSAVED");
  expect(vi.mocked(studyCommand).mock.calls.every(([, c]) => ["LIST", "READ", "RUNS"].includes(c.operation))).toBe(true);
  wrapper.unmount();
});

it("requests an ownership recheck on a current access error but ignores an old course failure", async () => {
  let rejectOld!: (reason: unknown) => void;
  vi.mocked(studyStatus).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }));
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "old" }, global: { stubs } });
  await flushPromises(); await wrapper.setProps({ taskId: "new" }); await flushPromises();
  rejectOld({ response: { status: 404 } }); await flushPromises();
  expect(wrapper.emitted("accessFailure")).toBeUndefined();
  vi.mocked(studyStatus).mockRejectedValueOnce({ response: { status: 403 } });
  await wrapper.setProps({ taskId: "revoked" }); await flushPromises();
  expect(wrapper.emitted("accessFailure")).toEqual([[]]);
  wrapper.unmount();
});
