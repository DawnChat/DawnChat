<template>
  <div class="msg-item-row assistant permission-row">
    <span class="msg-role">{{ agentLabel }}</span>
    <div class="msg-item permission-item">
      <div class="permission-title">{{ permissionRequiredLabel }} · {{ permission.tool }}</div>
      <p class="permission-status" :class="permission.status">{{ statusLabel }}</p>
      <p class="permission-detail">{{ permission.detail }}</p>
      <div class="permission-actions">
        <button class="permission-btn" :disabled="permission.status !== 'pending'" @click="emit('permission', permission.id, 'once')">
          {{ allowOnceLabel }}
        </button>
        <button
          class="permission-btn"
          :disabled="permission.status !== 'pending'"
          @click="emit('permission', permission.id, 'always', true)"
        >
          {{ alwaysAllowLabel }}
        </button>
        <button class="permission-btn danger" :disabled="permission.status !== 'pending'" @click="emit('permission', permission.id, 'reject')">
          {{ rejectLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface PermissionCardLite {
  id: string
  tool: string
  detail: string
  status: 'pending' | 'approved' | 'rejected'
}

const props = defineProps<{
  permission: PermissionCardLite
  agentLabel: string
  permissionRequiredLabel: string
  allowOnceLabel: string
  alwaysAllowLabel: string
  rejectLabel: string
}>()

const emit = defineEmits<{
  permission: [id: string, response: 'once' | 'always' | 'reject', remember?: boolean]
}>()

const statusLabel = computed(() => {
  if (props.permission.status === 'approved') return '已批准'
  if (props.permission.status === 'rejected') return '已拒绝'
  return '待确认'
})
</script>

<style scoped>
.msg-item-row {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.msg-item-row.assistant {
  align-items: flex-start;
}

.msg-role {
  display: block;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  padding: 0 0.1rem;
}

.msg-item {
  max-width: 92%;
  min-width: 0;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
}

.permission-row .msg-item {
  margin-left: 1.15rem;
  width: min(560px, calc(92% - 1.15rem));
}

.permission-item {
  background: var(--color-surface-2);
}

.permission-title {
  font-size: 0.82rem;
  font-weight: 600;
}

.permission-status {
  margin: 0.32rem 0 0 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.permission-status.approved {
  color: #2f855a;
}

.permission-status.rejected {
  color: #d9534f;
}

.permission-detail {
  margin: 0.42rem 0 0 0;
  font-size: 0.82rem;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
}

.permission-actions {
  margin-top: 0.55rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.permission-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface-3);
  color: var(--color-text);
  border-radius: 6px;
  height: 28px;
  padding: 0 0.6rem;
  font-size: 0.78rem;
  cursor: pointer;
}

.permission-btn.danger {
  color: #d9534f;
}

.permission-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>

