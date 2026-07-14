<script setup lang="ts">
defineProps<{
  title: string;
  description: string;
}>();
</script>

<template>
  <section class="empty-state">
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
    <div v-if="$slots.default" class="empty-state__action">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.empty-state {
  display: grid;
  justify-items: center;
  min-height: 260px;
  padding: 56px 24px;
  place-content: center;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface-subtle);
  text-align: center;
}

.empty-state h2 {
  margin: 0;
  color: var(--color-ink);
  font-size: 20px;
}

.empty-state p {
  max-width: 420px;
  margin: 10px 0 0;
  color: var(--color-ink-soft);
  line-height: 1.65;
}

.empty-state__action {
  margin-top: 22px;
}
</style>
