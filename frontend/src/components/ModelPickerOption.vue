<script setup lang="ts">
import type { ModelGuide } from "../lib/modelDiscovery";
defineProps<{ model: string; guide: ModelGuide; checked: boolean; disabled: boolean; status: string }>();
defineEmits<{ toggle: [model: string] }>();
</script>
<template>
  <div class="model-picker-row">
    <label>
      <input type="checkbox" :value="model" :checked="checked" :disabled="disabled" @change="$emit('toggle', model)" />
      <span class="model-info"><strong>{{ model }}</strong><small>{{ guide.description }}</small><span class="model-tags"><span>{{ guide.label }}</span><span v-if="guide.capability">{{ guide.capability }}</span><span>{{ status }}</span></span></span>
    </label>
    <a v-if="guide.source" :href="guide.source" target="_blank" rel="noopener noreferrer" :aria-label="`${model} 官方说明`">说明 ↗</a>
  </div>
</template>
<style scoped>
.model-picker-row{display:flex;align-items:flex-start;gap:8px;padding:9px 2px;border-bottom:1px solid var(--color-border)}
label{display:flex;align-items:flex-start;gap:9px;flex:1;min-width:0;cursor:pointer;margin:0;font-size:13px;font-weight:400}
input{flex-shrink:0;margin:3px 0 0;width:15px;height:15px;accent-color:var(--color-brand-strong)}
.model-info{display:grid;gap:4px;min-width:0;overflow-wrap:anywhere}strong{font-size:13px;font-weight:600}small{font-size:11px;color:var(--color-ink-muted);line-height:1.5}
.model-tags{display:flex;flex-wrap:wrap;gap:4px;font-size:10px;color:var(--color-ink-muted)}.model-tags>span{padding:2px 5px;border-radius:4px;background:var(--color-brand-soft)}
a{flex-shrink:0;font-size:11px;color:var(--color-brand-strong);padding:2px 0}
</style>
