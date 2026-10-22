<script setup lang="ts">
import { computed } from "vue";
import { singleTurnEvidence } from "../../api/modelUsage";
const props = defineProps<{ singleTurn?: unknown; model?: string; version?: number; mock?: boolean }>();
const evidence = computed(() => props.mock ? null : singleTurnEvidence(props.singleTurn, props.version));
</script>
<template>
  <div class="model-evidence" aria-label="模型证据等级">
    <p v-if="mock">本地确定性机制记录，不认证真实 Provider。</p>
    <ul>
      <li>模型发现：未验证（没有随此次选择保存目录证据）。目录可见仅证明模型目录可见。</li>
      <li>单轮协议：<template v-if="evidence">{{ evidence.ok ? '通过' : '失败' }} · {{ model }} · 连接 v{{ evidence.version }} · {{ new Date(evidence.checked_at * 1000).toISOString() }} · 来源：个人连接单次工具请求<template v-if="evidence.code"> · {{ evidence.code }}</template></template><template v-else>未验证（未记录适用证据）</template>。仅验证一次请求；适配器代码身份未记录，不认证当前适配器。</li>
      <li>多轮工具兼容：未验证。需要工具结果回填后的下一轮协议证据。</li>
      <li>真实课程质量：未验证。需要绑定冻结配置和数据集的独立评估。</li>
    </ul>
  </div>
</template>
<style scoped>
.model-evidence { color: var(--color-ink-soft); font-size: 13px; line-height: 1.7; }.model-evidence ul { padding-left: 20px; }
</style>
