<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string;
    tone?: "neutral" | "progress" | "success" | "warning" | "danger";
  }>(),
  {
    tone: "neutral",
  },
);
</script>

<template>
  <span class="status-badge" :class="`status-badge--${tone}`">{{ label }}</span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
  color: var(--color-ink-soft);
  font-size: 12px;
  font-weight: 680;
  white-space: nowrap;
}

.status-badge--progress {
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
}

.status-badge--success {
  background: var(--color-success-surface);
  color: var(--color-success);
}

.status-badge--warning {
  background: var(--color-evidence-surface);
  color: var(--color-warning);
}

.status-badge--danger {
  background: var(--color-danger-surface);
  color: var(--color-danger);
}
</style>
