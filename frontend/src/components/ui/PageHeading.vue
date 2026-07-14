<script setup lang="ts">
defineProps<{
  eyebrow?: string;
  title: string;
  description?: string;
}>();
</script>

<template>
  <header class="page-heading">
    <div>
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="page-heading__description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-heading__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.page-heading h1 {
  margin: 8px 0 0;
  color: var(--color-ink);
  font-size: clamp(30px, 4vw, 42px);
  font-weight: 720;
  letter-spacing: -0.035em;
  line-height: 1.12;
}

.page-heading__description {
  max-width: 680px;
  margin: 12px 0 0;
  color: var(--color-ink-soft);
  font-size: 15px;
  line-height: 1.7;
}

.page-heading__actions {
  flex: 0 0 auto;
}

@media (max-width: 680px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .page-heading__actions,
  .page-heading__actions :deep(.el-button),
  .page-heading__actions :deep(a) {
    width: 100%;
  }
}
</style>
