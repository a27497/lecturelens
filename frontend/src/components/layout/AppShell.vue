<script setup lang="ts">
import { RouterView } from "vue-router";
import AppHeader from "./AppHeader.vue";
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <div class="app-shell__content">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--color-canvas);
}

.app-shell__content {
  min-height: calc(100vh - var(--header-height));
}
</style>
