<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Close, Menu } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";
import { useAppStore } from "../../stores/app";
import { useAuthStore } from "../../stores/auth";

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const authStore = useAuthStore();
const mobileOpen = ref(false);

const navItems = computed(() =>
  authStore.isAuthenticated
    ? [
        { label: "我的课程", to: "/tasks" },
        { label: "上传课程", to: "/upload" },
      ]
    : [{ label: "首页", to: "/" }],
);

watch(
  () => route.fullPath,
  () => {
    mobileOpen.value = false;
  },
);

function logout() {
  authStore.logout();
  void router.push("/");
}
</script>

<template>
  <header class="app-header">
    <div class="app-header__inner">
      <RouterLink class="app-header__brand" to="/" aria-label="LectureLens 首页">
        {{ appStore.appName }}
      </RouterLink>

      <nav class="app-header__nav" aria-label="主导航">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="app-header__account">
        <template v-if="authStore.isAuthenticated">
          <span class="app-header__email" :title="authStore.displayEmail">
            {{ authStore.displayEmail }}
          </span>
          <button class="app-header__text-button" type="button" @click="logout">退出</button>
        </template>
        <template v-else>
          <RouterLink class="app-header__login" to="/login">登录</RouterLink>
          <RouterLink class="app-header__register" to="/register">创建账号</RouterLink>
        </template>
      </div>

      <button
        class="app-header__menu-button"
        type="button"
        :aria-expanded="mobileOpen"
        aria-controls="mobile-navigation"
        :aria-label="mobileOpen ? '关闭导航' : '打开导航'"
        @click="mobileOpen = !mobileOpen"
      >
        <el-icon :size="20">
          <Close v-if="mobileOpen" />
          <Menu v-else />
        </el-icon>
      </button>
    </div>

    <nav v-if="mobileOpen" id="mobile-navigation" class="app-header__mobile" aria-label="移动端导航">
      <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
        {{ item.label }}
      </RouterLink>
      <template v-if="authStore.isAuthenticated">
        <span class="app-header__mobile-email">{{ authStore.displayEmail }}</span>
        <button type="button" @click="logout">退出登录</button>
      </template>
      <template v-else>
        <RouterLink to="/login">登录</RouterLink>
        <RouterLink to="/register">创建账号</RouterLink>
      </template>
    </nav>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  z-index: 30;
  top: 0;
  border-bottom: 1px solid var(--color-border);
  background: rgb(255 255 255 / 96%);
  backdrop-filter: blur(12px);
}

.app-header__inner {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  width: min(calc(100% - 48px), 1360px);
  height: var(--header-height);
  margin: 0 auto;
}

.app-header__brand {
  justify-self: start;
  color: var(--color-ink);
  font-size: 18px;
  font-weight: 760;
  letter-spacing: -0.025em;
  text-decoration: none;
}

.app-header__nav,
.app-header__account {
  display: flex;
  align-items: center;
  gap: 24px;
}

.app-header__nav a,
.app-header__login,
.app-header__text-button {
  color: var(--color-ink-soft);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
}

.app-header__nav a.router-link-active {
  color: var(--color-ink);
  font-weight: 720;
}

.app-header__account {
  justify-self: end;
  gap: 14px;
}

.app-header__email {
  max-width: 180px;
  color: var(--color-ink-muted);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header__text-button {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.app-header__register {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 15px;
  border-radius: var(--radius-sm);
  background: var(--color-ink);
  color: #ffffff;
  font-size: 14px;
  font-weight: 650;
  text-decoration: none;
}

.app-header__menu-button,
.app-header__mobile {
  display: none;
}

@media (max-width: 760px) {
  .app-header__inner {
    grid-template-columns: 1fr auto;
    width: min(calc(100% - 32px), 1360px);
  }

  .app-header__nav,
  .app-header__account {
    display: none;
  }

  .app-header__menu-button {
    display: inline-grid;
    width: 44px;
    height: 44px;
    padding: 0;
    place-items: center;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface);
    color: var(--color-ink);
    cursor: pointer;
  }

  .app-header__mobile {
    display: grid;
    gap: 2px;
    padding: 8px 16px 16px;
    border-top: 1px solid var(--color-border);
    background: var(--color-surface);
  }

  .app-header__mobile a,
  .app-header__mobile button,
  .app-header__mobile-email {
    width: 100%;
    padding: 12px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-ink-soft);
    font-size: 15px;
    text-align: left;
    text-decoration: none;
  }

  .app-header__mobile a.router-link-active {
    background: var(--color-brand-soft);
    color: var(--color-brand-strong);
  }

  .app-header__mobile button {
    cursor: pointer;
  }

  .app-header__mobile-email {
    color: var(--color-ink-muted);
    overflow-wrap: anywhere;
  }
}
</style>
