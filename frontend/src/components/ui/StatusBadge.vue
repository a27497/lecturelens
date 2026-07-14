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
  border: 1px solid #d8ded9;
  border-radius: 999px;
  background: #f4f6f4;
  color: var(--color-ink-soft);
  font-size: 12px;
  font-weight: 680;
  white-space: nowrap;
}

.status-badge--progress {
  border-color: #b9d2c8;
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
}

.status-badge--success {
  border-color: #a8cab9;
  background: #edf6f0;
  color: var(--color-success);
}

.status-badge--warning {
  border-color: #ddc6a9;
  background: #fbf5ec;
  color: var(--color-warning);
}

.status-badge--danger {
  border-color: #e0b9b6;
  background: #fbefee;
  color: var(--color-danger);
}
</style>
