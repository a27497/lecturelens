import { createRouter, createWebHistory } from "vue-router";
import Home from "../pages/Home.vue";
import { useAuthStore } from "../stores/auth";
import LoginView from "../views/LoginView.vue";
import RegisterView from "../views/RegisterView.vue";
import TaskDetailView from "../views/TaskDetailView.vue";
import TaskListView from "../views/TaskListView.vue";
import UploadView from "../views/UploadView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
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

router.beforeEach((to) => {
  const authStore = useAuthStore();
  const isAuthenticated = authStore.isAuthenticated;

  if (to.meta.requiresAuth && !isAuthenticated) {
    return {
      path: "/login",
      query: { redirect: to.fullPath },
    };
  }

  if (to.meta.guestOnly && isAuthenticated) {
    const redirect = typeof to.query.redirect === "string" ? to.query.redirect : "/upload";
    return redirect;
  }

  return true;
});
