import { createRouter, createWebHistory } from "vue-router";
import RecruiterDemoView from "../views/RecruiterDemoView.vue";
import Home from "../pages/Home.vue";
import { useAuthStore } from "../stores/auth";
import LoginView from "../views/LoginView.vue";
import RegisterView from "../views/RegisterView.vue";
import TaskDetailView from "../views/TaskDetailView.vue";
import TaskListView from "../views/TaskListView.vue";
import UploadView from "../views/UploadView.vue";
import ModelManagementView from "../views/ModelManagementView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/admin/settings/models", name: "admin-models", component: () => import("../views/AdminModelManagementView.vue"), meta: { requiresAuth: true, requiresAdmin: true } },
    { path: "/demo", name: "recruiter-demo", component: RecruiterDemoView },
    { path: "/settings/models", name: "models", component: ModelManagementView, meta: { requiresAuth: true } },
    {
      path: "/",
      name: "home",
      component: Home,
    },
    {
      path: "/login",
      name: "login",
      component: LoginView,
      meta: { guestOnly: true },
    },
    {
      path: "/register",
      name: "register",
      component: RegisterView,
      meta: { guestOnly: true },
    },
    {
      path: "/upload",
      name: "upload",
      component: UploadView,
      meta: { requiresAuth: true },
    },
    {
      path: "/tasks",
      name: "tasks",
      component: TaskListView,
      meta: { requiresAuth: true },
    },
    {
      path: "/tasks/:taskId",
      name: "task-detail",
      component: TaskDetailView,
      meta: { requiresAuth: true },
    },
  ],
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();
  const isAuthenticated = authStore.isAuthenticated;

  if (to.meta.requiresAuth && !isAuthenticated) {
    return {
      path: "/login",
      query: { redirect: to.fullPath },
    };
  }

  if (to.meta.requiresAdmin) {
    try { await authStore.loadCurrentUser(true); }
    catch { return { path: "/tasks" }; }
    if (!authStore.isAdmin) return { path: "/tasks" };
  }

  if (to.meta.guestOnly && isAuthenticated) {
    const redirect = typeof to.query.redirect === "string" ? to.query.redirect : "/upload";
    return redirect;
  }

  return true;
});
