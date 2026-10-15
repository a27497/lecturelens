import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import { studyCommand } from "../../api/study";
import StudyApprovalPanel from "./StudyApprovalPanel.vue";

vi.mock("../../api/study", () => ({ studyCommand: vi.fn() }));
const stubs = {
  "el-input": { props: ["modelValue"], emits: ["update:modelValue"], template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
  "el-button": { props: ["disabled"], template: '<button :disabled="disabled"><slot /></button>' },
};
const props = { taskId: "task", sessionId: "session", runId: "run", approval: { kind: "practice" as const, decision: null, preview: { title: "Draft", explanation: "original", questions: [{ question: "Why stop?", evidence_ids: ["e1"] }] } } };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(studyCommand).mockResolvedValue({}); });
it.each(["approve", "reject"] as const)("sends a scoped %s decision", async decision => {
  const wrapper = mount(StudyApprovalPanel, { props, global: { stubs } });
  await wrapper.findAll("button").find(b => b.text() === (decision === "approve" ? "批准发布" : "拒绝发布"))!.trigger("click");
  await flushPromises();
  expect(studyCommand).toHaveBeenCalledWith("task", expect.objectContaining({ operation: "DECIDE_APPROVAL", session_id: "session", run_id: "run", approval_decision: decision, request_key: expect.any(String) }));
  expect(wrapper.emitted("decided")).toHaveLength(1);
});
it("edits publication text and preserves the same request key after a lost response", async () => {
  vi.mocked(studyCommand).mockRejectedValueOnce(new Error("lost")).mockResolvedValue({});
  const wrapper = mount(StudyApprovalPanel, { props, global: { stubs } });
  await wrapper.findAll("button").find(b => b.text() === "修改后批准")!.trigger("click");
  await wrapper.find("textarea").setValue("human explanation");
  const confirm = wrapper.findAll("button").find(b => b.text() === "确认修改并批准")!;
  await confirm.trigger("click"); await flushPromises();
  await confirm.trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls[0]![1]).toEqual(vi.mocked(studyCommand).mock.calls[1]![1]);
  expect(vi.mocked(studyCommand).mock.calls[0]![1].approval_edit).toBe("human explanation");
});
