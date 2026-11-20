import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import CourseNotesPanel from "./CourseNotesPanel.vue";
import { courseNotesKey, readCourseNotes, type NoteAnchor } from "./courseNotes";

const citation: NoteAnchor = { kind: "evidence", evidenceId: "subtitle-r3", revision: 3, milliseconds: 12000 };
const account = { userId: 7, taskId: "course-A" };
const key = courseNotesKey(account.userId, account.taskId);

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("personal course notes", () => {
  it("restores an evidence note, emits its revision, and deletes after confirmation", async () => {
    const first = mount(CourseNotesPanel, { props: { ...account, citation } });
    await first.get("textarea").setValue("书写自己的理解");
    await first.get("form").trigger("submit");
    expect(readCourseNotes(localStorage, key)).toEqual([
      { id: expect.any(String), text: "书写自己的理解", anchor: citation },
    ]);
    expect(first.get("[role=status]").text()).toContain("笔记已保存");
    first.unmount();

    const reopened = mount(CourseNotesPanel, { props: account });
    expect(reopened.text()).toContain("书写自己的理解");
    await reopened.get(".note-time--link").trigger("click");
    expect(reopened.emitted("jump")).toEqual([[citation]]);
    await reopened.get(".note-button--danger").trigger("click");
    expect(readCourseNotes(localStorage, key)).toHaveLength(1);
    await reopened.get(".note-button--danger").trigger("click");
    expect(readCourseNotes(localStorage, key)).toEqual([]);
    reopened.unmount();
  });

  it("scopes both saved notes and drafts and captures the playback position when typing starts", async () => {
    const panel = mount(CourseNotesPanel, { props: { ...account, playbackMs: 1500 } });
    await panel.get("textarea").setValue("仅此课程");
    await panel.setProps({ playbackMs: 4000 });
    await panel.get("form").trigger("submit");
    expect(readCourseNotes(localStorage, key)[0]?.anchor).toEqual({ kind: "playback", milliseconds: 1500 });
    await panel.get("textarea").setValue("未保存");
    await panel.setProps({ userId: 9 });
    expect(panel.text()).not.toContain("仅此课程");
    expect(panel.get("textarea").element.value).toBe("");
    await panel.setProps({ userId: account.userId, taskId: "course-B" });
    expect(panel.text()).not.toContain("仅此课程");
    await panel.setProps(account);
    expect(panel.text()).toContain("仅此课程");
    panel.unmount();
  });

  it.each([
    "invalid json",
    "{}",
    '[{"id":"broken","text":"不可显示","anchor":{"kind":"evidence","milliseconds":12,"evidenceId":"v1","revision":"1"}}]',
    '[{"id":"broken","text":"不可显示","anchor":{"kind":"playback","milliseconds":-1}}]',
  ])("keeps an invalid storage record hidden and preserves the draft", async raw => {
    localStorage.setItem(key, raw);
    const panel = mount(CourseNotesPanel, { props: account });
    expect(panel.get("[role=alert]").text()).toContain("无法读取");
    expect(panel.text()).not.toContain("不可显示");
    await panel.get("textarea").setValue("重试后保存");
    await panel.get("form").trigger("submit");
    expect(panel.get("[role=alert]").text()).toContain("无法更新");
    expect(panel.get("textarea").element.value).toBe("重试后保存");
    expect(localStorage.getItem(key)).toBe(raw);
    panel.unmount();
  });

  it("surfaces a browser write failure and leaves the draft in place", async () => {
    const panel = mount(CourseNotesPanel, { props: account });
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new DOMException("Full", "QuotaExceededError"); });
    await panel.get("textarea").setValue("等待重试");
    await panel.get("form").trigger("submit");
    expect(panel.get("[role=alert]").text()).toContain("无法更新");
    expect(panel.get("textarea").element.value).toBe("等待重试");
    panel.unmount();
  });
});
