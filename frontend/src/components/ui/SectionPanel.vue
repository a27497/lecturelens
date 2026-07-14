<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    subtle?: boolean;
  }>(),
  {
    title: "",
    description: "",
    subtle: false,
  },
);
</script>

<template>
  <section class="section-panel" :class="{ 'section-panel--subtle': subtle }">
    <header v-if="title || description || $slots.header" class="section-panel__header">
      <slot name="header">
        <div>
          <h2 v-if="title">{{ title }}</h2>
          <p v-if="description">{{ description }}</p>
        </div>
      </slot>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.section-panel {
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-low);
}

.section-panel--subtle {
  background: var(--color-surface-subtle);
  box-shadow: none;
}

.section-panel__header {
  margin-bottom: 22px;
}

.section-panel h2 {
  margin: 0;
  color: var(--color-ink);
  font-size: 20px;
  line-height: 1.3;
}

.section-panel p {
  margin: 7px 0 0;
  color: var(--color-ink-soft);
  line-height: 1.65;
}

@media (max-width: 640px) {
  .section-panel {
    padding: 20px;
  }
}
</style>
