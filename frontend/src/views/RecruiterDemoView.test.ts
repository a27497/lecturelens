import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import RecruiterDemoView from "./RecruiterDemoView.vue";
const mocks = vi.hoisted(() => ({ login: vi.fn(), push: vi.fn() }));
vi.mock("../stores/auth", () => ({ useAuthStore: () => ({ login: mocks.login }) }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("../recruiterDemo", () => ({ recruiterDemoEnabled: true, recruiterDemo: { taskId: "sample", email: "demo@example.com", password: "public-demo" } }));
vi.mock("../api/auth", () => ({ toReadableAuthError: () => "登录未确认，请重试" }));
const create = () => mount(RecruiterDemoView, { global: { stubs: { "el-button": { template: '<button><slot /></button>' } } } });
beforeEach(() => vi.resetAllMocks());
it("enters through normal Java authentication without uploading or injecting a token", async () => {
  mocks.login.mockResolvedValue({});
  const wrapper = create();
  expect(mocks.login).not.toHaveBeenCalled();
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(mocks.login).toHaveBeenCalledWith({ email: "demo@example.com", password: "public-demo" });
  expect(mocks.push).toHaveBeenCalledWith("/tasks/sample");
  expect(wrapper.text()).toContain("共享演示账号");
});
it("keeps failed login visible and never navigates past authentication", async () => {
  mocks.login.mockRejectedValue(new Error("401"));
  const wrapper = create(); await wrapper.find("button").trigger("click"); await flushPromises();
  expect(mocks.push).not.toHaveBeenCalled();
  expect(wrapper.find('[role="alert"]').text()).toContain("登录未确认");
});
it("prevents duplicate logins while the first request is pending", async () => {
  mocks.login.mockImplementation(() => new Promise(() => {}));
  const wrapper = create();
  await wrapper.find("button").trigger("click"); await wrapper.find("button").trigger("click");
  expect(mocks.login).toHaveBeenCalledTimes(1);
});
