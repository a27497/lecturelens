import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import Home from "./Home.vue";

const create = () => mount(Home, {
  global: {
    stubs: {
      RouterLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
    },
  },
});

it("offers the sample course, engineering sections, and source evidence", () => {
  const wrapper = create();
  expect(wrapper.find("h1").text()).toContain("Study Agent");
  expect(wrapper.findAll('a[href="/demo"]')).toHaveLength(3);
  expect(wrapper.find('a[href="#engineering"]').exists()).toBe(true);
  expect(wrapper.find("#engineering").exists()).toBe(true);
  expect(wrapper.find('a[href="https://github.com/a27497/lecturelens"]').attributes("rel")).toBe("noopener noreferrer");
  expect(wrapper.find('a[href*="HUMAN_ACCEPTANCE_REPORT.md"]').exists()).toBe(true);
  expect(wrapper.find(".hero__visual img").attributes("src")).toBe("/images/lecturelens-course-reading.webp");
  expect(wrapper.findAll(".demo-section__visual img").map((image) => image.attributes("src"))).toEqual([
    "/images/recruiter-agent-evidence.webp",
    "/images/recruiter-agent-trace.webp",
  ]);
});
