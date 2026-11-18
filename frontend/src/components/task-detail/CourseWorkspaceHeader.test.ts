import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import CourseWorkspaceHeader from "./CourseWorkspaceHeader.vue";

const base = { canCancel: false, canRetry: false, refreshing: false, cancelLoading: false, retryLoading: false, status: "SUCCEEDED" as const };
const stubs = { RouterLink: { template: "<a><slot /></a>" }, "el-tag": { template: "<span><slot /></span>" }, "el-button": { template: "<button><slot /></button>" } };

describe("course workspace header", () => {
  it("shows the owner's course name as plain text with the full name in the title", () => {
    const name = "<img src=x onerror=alert(1)> week 2 lecture";
    const w = mount(CourseWorkspaceHeader, { props: { ...base, courseName: name }, global: { stubs } });
    const title = w.get("h1");
    expect(title.text()).toBe(name);
    expect(title.attributes("title")).toBe(name);
    expect(title.find("img").exists()).toBe(false);
    expect(title.classes()).toContain("workspace-header__title");
  });

  it("falls back to the generic title without a course name", () => {
    const w = mount(CourseWorkspaceHeader, { props: { ...base, courseName: null }, global: { stubs } });
    expect(w.get("h1").text()).toBe("课程学习");
    expect(w.get("h1").attributes("title")).toBeUndefined();
  });
});
