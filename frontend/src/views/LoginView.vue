<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { toReadableAuthError } from "../api/auth";
import { fetchPublicRuntimeConfiguration } from "../api/runtimeConfiguration";
import { useAuthStore } from "../stores/auth";
import { validateLoginForm } from "../utils/authFormValidation";
import {
  loginCredentialPolicy,
  type LoginCredentialMode,
} from "../utils/loginCredentialPolicy";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const errorMessage = ref("");
const credentialMode = ref<LoginCredentialMode | "loading">("loading");
const credentialEntryEnabled = reactive({ email: false, password: false });

const form = reactive({
  email: "",
  password: "",
});

const credentialPolicy = computed(() => loginCredentialPolicy(
  credentialMode.value === "demo" ? "demo" : "real",
));

onMounted(async () => {
  let mode: LoginCredentialMode = "real";
  try {
    mode = (await fetchPublicRuntimeConfiguration()).demoMode ? "demo" : "real";
  } catch {
    // A failed mode check must not re-enable Demo credential autofill.
    mode = "real";
  }
  form.email = "";
  form.password = "";
  credentialEntryEnabled.email = false;
  credentialEntryEnabled.password = false;
  credentialMode.value = mode;
});

async function submitLogin() {
  const validationError = validateLoginForm(form);
  if (validationError) {
    errorMessage.value = validationError;
    return;
  }

  errorMessage.value = "";
  try {
    await authStore.login({
      email: form.email.trim(),
      password: form.password,
    });
    ElMessage.success("登录成功");
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/upload";
    await router.push(redirect);
  } catch (error) {
    errorMessage.value = toReadableAuthError(error);
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-panel" aria-labelledby="login-title">
      <div class="auth-panel__header">
        <p class="eyebrow">LectureLens</p>
        <h1 id="login-title">登录</h1>
        <p>查看已上传的视频和处理结果。</p>
      </div>

      <el-alert
        v-if="errorMessage"
        :closable="false"
        :title="errorMessage"
        show-icon
        type="error"
      />

      <el-form
        v-if="credentialMode !== 'loading'"
        :key="credentialMode"
        class="auth-form"
        :autocomplete="credentialPolicy.formAutocomplete"
        label-position="top"
        @submit.prevent="submitLogin"
      >
        <el-form-item label="邮箱">
          <el-input
            v-model="form.email"
            :autocomplete="credentialPolicy.emailAutocomplete"
            :name="credentialPolicy.emailName"
            placeholder="you@example.com"
            :readonly="credentialPolicy.preventInitialAutofill && !credentialEntryEnabled.email"
            size="large"
            @focus="credentialEntryEnabled.email = true"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :autocomplete="credentialPolicy.passwordAutocomplete"
            :name="credentialPolicy.passwordName"
            placeholder="请输入密码"
            :readonly="credentialPolicy.preventInitialAutofill && !credentialEntryEnabled.password"
            show-password
            size="large"
            type="password"
            @focus="credentialEntryEnabled.password = true"
            @keyup.enter="submitLogin"
          />
        </el-form-item>
        <el-button
          class="auth-form__submit"
          :loading="authStore.loading"
          native-type="submit"
          size="large"
          type="primary"
        >
          登录
        </el-button>
      </el-form>

      <div class="auth-panel__footer">
        <p>没有账号？<RouterLink to="/register">创建账号</RouterLink></p>
        <RouterLink to="/">返回首页</RouterLink>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  display: grid;
  min-height: calc(100vh - var(--header-height));
  padding: 52px 24px;
  place-items: center;
}

.auth-panel {
  display: grid;
  gap: 22px;
  width: min(100%, 440px);
  padding: 34px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-low);
}

.auth-panel__header h1 {
  margin: 9px 0 0;
  color: var(--color-ink);
  font-size: 29px;
  letter-spacing: -0.03em;
}

.auth-panel__header > p:last-child {
  margin: 10px 0 0;
  color: var(--color-ink-soft);
  line-height: 1.6;
}

.auth-form {
  display: grid;
  gap: 4px;
}

.auth-form__submit {
  width: 100%;
  margin-top: 4px;
}

.auth-panel__footer {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding-top: 18px;
  border-top: 1px solid var(--color-border);
  color: var(--color-ink-muted);
  font-size: 14px;
}

.auth-panel__footer p {
  margin: 0;
}

.auth-panel__footer a {
  color: var(--color-brand-strong);
  font-weight: 650;
  text-decoration: none;
}

@media (max-width: 520px) {
  .auth-page {
    align-items: start;
    padding: 32px 16px;
  }

  .auth-panel {
    padding: 24px;
  }

  .auth-panel__footer {
    flex-direction: column;
  }
}
</style>
