import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { router } from "./index";
import { useAuthStore } from "../stores/auth";
import { currentUser } from "../api/auth";
import AppHeader from "../components/layout/AppHeader.vue";

vi.mock("../api/auth", async original => ({ ...await original<typeof import("../api/auth")>(), currentUser: vi.fn() }));
let pinia: ReturnType<typeof createPinia>;
let auth: ReturnType<typeof useAuthStore>;
let page: ReturnType<typeof mount> | undefined;
beforeEach(async () => {
  vi.resetAllMocks(); localStorage.clear(); pinia = createPinia(); setActivePinia(pinia); auth = useAuthStore();
  auth.$patch({ accessToken: "test-token", user: { userId: 1, email: "user@example.invalid", status: "ACTIVE", role: "USER" } });
  vi.mocked(currentUser).mockResolvedValue({ userId: 1, email: "user@example.invalid", status: "ACTIVE", role: "USER" });
  await router.push("/tasks");
});
afterEach(() => { page?.unmount(); page = undefined; localStorage.clear(); });

it("keeps the personal route separate and redirects unauthenticated administrator navigation to login", async () => {
  expect(router.resolve("/settings/models").name).toBe("models");
  expect(router.resolve("/admin/settings/models").name).toBe("admin-models");
  auth.accessToken = "";
  await router.push("/admin/settings/models");
  expect(router.currentRoute.value.path).toBe("/login");
  expect(router.currentRoute.value.query.redirect).toBe("/admin/settings/models");
  expect(currentUser).not.toHaveBeenCalled();
});

it("refreshes the server role before allowing direct administrator URLs, including revoked roles", async () => {
  auth.user!.role = "ADMIN";
  await router.push("/admin/settings/models");
  expect(currentUser).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe("/tasks");
  expect(auth.isAdmin).toBe(false);
  vi.mocked(currentUser).mockResolvedValueOnce({ userId: 1, email: "admin@example.invalid", status: "ACTIVE", role: "ADMIN" });
  await router.push("/admin/settings/models");
  expect(router.currentRoute.value.path).toBe("/admin/settings/models");
  expect(auth.isAdmin).toBe(true);
});

it("hides the administrator entrance from ordinary users while preserving the personal entrance", async () => {
  page = mount(AppHeader, { global: { plugins: [pinia, router], stubs: { "el-icon": true } } });
  await flushPromises();
  expect(page.find('a[href="/settings/models"]').exists()).toBe(true);
  expect(page.find('a[href="/admin/settings/models"]').exists()).toBe(false);
  auth.user!.role = "ADMIN"; await flushPromises();
  expect(page.find('a[href="/admin/settings/models"]').exists()).toBe(true);
  auth.user!.role = "USER"; await flushPromises();
  expect(page.find('a[href="/admin/settings/models"]').exists()).toBe(false);
});

it("restores the navigation role from /api/me after reload without persisting a role", async () => {
  auth.user = null;
  vi.mocked(currentUser).mockResolvedValueOnce({ userId: 1, email: "admin@example.invalid", status: "ACTIVE", role: "ADMIN" });
  const storage = vi.spyOn(Storage.prototype, "setItem");
  page = mount(AppHeader, { global: { plugins: [pinia, router], stubs: { "el-icon": true } } });
  await flushPromises();
  expect(currentUser).toHaveBeenCalledOnce();
  expect(page.find('a[href="/admin/settings/models"]').exists()).toBe(true);
  expect(storage).not.toHaveBeenCalled(); storage.mockRestore();
});

it("denies access and removes the cached role when the current role cannot be read", async () => {
  auth.user!.role = "ADMIN";
  vi.mocked(currentUser).mockRejectedValueOnce(new Error("network unavailable"));
  await router.push("/admin/settings/models");
  expect(router.currentRoute.value.path).toBe("/tasks");
  expect(auth.isAdmin).toBe(false);
});

it("uses the course library after login while preserving explicit course redirects", async () => {
  expect(router.resolve('/upload').name).toBe('upload');
  expect(router.resolve('/tasks').name).toBe('tasks');
  await router.push('/'); expect(router.currentRoute.value.path).toBe('/tasks');
  await router.push('/login'); expect(router.currentRoute.value.path).toBe('/tasks');
  await router.push('/login?redirect=/tasks/course-old?layout=classic');
  expect(router.currentRoute.value.path).toBe('/tasks/course-old');
  expect(router.currentRoute.value.query.layout).toBe('classic');
});
