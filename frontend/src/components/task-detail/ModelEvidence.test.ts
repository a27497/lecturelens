import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import ModelEvidence from "./ModelEvidence.vue";

const check = { ok: true, code: null, checked_at: 1700000000, version: 1 };
const malformed = [
  { ...check, checked_at: undefined }, { ...check, checked_at: null },
  { ...check, checked_at: "1700000000" }, { ...check, checked_at: "invalid" },
  { ...check, checked_at: true }, { ...check, checked_at: -1 },
  { ...check, checked_at: 1e20 }, { ...check, checked_at: 1.5 },
  { ...check, ok: "false" }, { ...check, ok: 1 },
  { ...check, version: true }, { ...check, version: "1" },
  { ...check, version: undefined }, { ...check, version: 2 },
  { ...check, code: "https://private-endpoint.invalid/secret" },
  { ...check, code: "MODEL_CHECK_FAILED" }, "legacy-string", [check],
];
it.each(malformed)("treats malformed historical evidence as unverified without a render error: %j", singleTurn => {
  const onError = vi.fn();
  const wrapper = mount(ModelEvidence, { props: { singleTurn: singleTurn as never, version: 1, model: "historical-model" }, global: { config: { errorHandler: onError } } });
  expect(onError).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("单轮协议：未验证");
  expect(wrapper.text()).not.toContain("private-endpoint");
  wrapper.unmount();
});
it("does not certify a real provider from Mock observations", () => {
  const wrapper = mount(ModelEvidence, { props: { singleTurn: check, version: 1, model: "fixture", mock: true } });
  expect(wrapper.text()).toContain("单轮协议：未验证"); wrapper.unmount();
});
it("keeps well-formed single-turn success and failure limited to their own version", () => {
  for (const ok of [true, false]) {
    const wrapper = mount(ModelEvidence, { props: { singleTurn: { ...check, ok, code: ok ? null : "MODEL_CHECK_TIMEOUT" }, version: 1, model: "historical-model" } });
    expect(wrapper.text()).toContain(ok ? "单轮协议：通过" : "单轮协议：失败");
    expect(wrapper.text()).toContain("2023-11-14T22:13:20.000Z");
    expect(wrapper.text()).toContain("多轮工具兼容：未验证");
    expect(wrapper.text()).toContain("真实课程质量：未验证"); wrapper.unmount();
  }
});
