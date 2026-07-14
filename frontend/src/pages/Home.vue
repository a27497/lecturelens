<script setup lang="ts">
import { computed } from "vue";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();

const primaryTarget = computed(() =>
  authStore.isAuthenticated ? "/upload" : "/login?redirect=/upload",
);
const secondaryTarget = computed(() => (authStore.isAuthenticated ? "/tasks" : "/login"));
</script>

<template>
  <main class="home-page">
    <div class="page-container home-page__inner">
      <section class="home-hero" aria-labelledby="home-title">
        <p class="eyebrow">LectureLens</p>
        <h1 id="home-title">课程视频，也可以像文档一样阅读</h1>
        <p class="home-hero__summary">
          上传课程录屏、讲座或网课视频，按时间查看字幕、中文翻译、课程摘要和下载文件。
        </p>
        <div class="home-hero__actions">
          <RouterLink :to="primaryTarget">
            <el-button size="large" type="primary">上传课程</el-button>
          </RouterLink>
          <RouterLink class="home-hero__secondary" :to="secondaryTarget">
            查看我的课程
          </RouterLink>
        </div>
      </section>

      <section class="home-process" aria-labelledby="process-title">
        <div class="home-process__heading">
          <h2 id="process-title">使用方法</h2>
        </div>
        <ol class="home-process__steps">
          <li>
            <span>01</span>
            <div>
              <strong>选择视频</strong>
              <p>选择本地课程录屏、讲座或网课视频。</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>整理内容</strong>
              <p>系统整理字幕、翻译和学习资料。</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>阅读与查找</strong>
              <p>按时间阅读课程内容，查看重点或下载文件。</p>
            </div>
          </li>
        </ol>
      </section>
    </div>
  </main>
</template>

<style scoped>
.home-page {
  padding: clamp(56px, 8vw, 104px) 0 72px;
}

.home-page__inner {
  display: grid;
  gap: clamp(64px, 9vw, 108px);
}

.home-hero {
  max-width: 780px;
  padding-top: 18px;
}

.home-hero h1 {
  max-width: 720px;
  margin: 18px 0 0;
  color: var(--color-ink);
  font-size: clamp(40px, 4.6vw, 56px);
  font-weight: 700;
  letter-spacing: -0.045em;
  line-height: 1.12;
}

.home-hero__summary {
  max-width: 680px;
  margin: 26px 0 0;
  color: var(--color-ink-soft);
  font-size: clamp(17px, 2vw, 20px);
  line-height: 1.75;
}

.home-hero__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 22px;
  margin-top: 34px;
}

.home-hero__actions a {
  text-decoration: none;
}

.home-hero__secondary {
  color: var(--color-brand-strong);
  font-size: 15px;
  font-weight: 680;
}

.home-hero__secondary::after {
  content: " →";
}

.home-process {
  display: grid;
  grid-template-columns: minmax(190px, 0.7fr) minmax(0, 2fr);
  gap: 52px;
  padding-top: 34px;
  border-top: 1px solid var(--color-border);
}

.home-process__heading h2 {
  margin: 0;
  color: var(--color-ink);
  font-size: 25px;
  letter-spacing: -0.025em;
}

.home-process__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 36px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-process__steps li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 14px;
}

.home-process__steps span {
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 750;
  line-height: 1.8;
}

.home-process__steps strong {
  color: var(--color-ink);
  font-size: 16px;
}

.home-process__steps p {
  margin: 8px 0 0;
  color: var(--color-ink-muted);
  font-size: 14px;
  line-height: 1.65;
}

@media (max-width: 820px) {
  .home-process {
    grid-template-columns: 1fr;
    gap: 28px;
  }

  .home-process__steps {
    gap: 22px;
  }
}

@media (max-width: 620px) {
  .home-page {
    padding: 44px 0 52px;
  }

  .home-page__inner {
    gap: 64px;
  }

  .home-hero h1 {
    font-size: 34px;
    letter-spacing: -0.035em;
  }

  .home-hero__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .home-hero__actions :deep(.el-button),
  .home-hero__actions a {
    width: 100%;
  }

  .home-hero__secondary {
    padding: 8px 0;
    text-align: center;
  }

  .home-process__steps {
    grid-template-columns: 1fr;
  }
}
</style>
