<template>
  <div class="todo-dock">
    <button class="todo-header" type="button" @click="collapsed = !collapsed">
      <span class="todo-title">{{ title }} {{ completedCount }}/{{ todos.length }}</span>
      <span v-if="collapsed && activeTodo" class="todo-preview">{{ activeTodo.content }}</span>
      <span class="todo-toggle">{{ collapsed ? expandLabel : collapseLabel }}</span>
    </button>
    <div v-show="!collapsed" class="todo-list">
      <div
        v-for="todo in todos"
        :key="todo.id"
        class="todo-item"
        :data-status="todo.status"
        :data-active="todo.id === activeTodo?.id"
      >
        <span class="todo-mark">{{ todoMark(todo.status) }}</span>
        <span class="todo-content">{{ todo.content }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface TodoItemLite {
  id: string
  content: string
  status: string
}

const props = defineProps<{
  todos: TodoItemLite[]
  title: string
  collapseLabel: string
  expandLabel: string
}>()

const collapsed = ref(false)
const completedCount = computed(() => props.todos.filter((todo) => todo.status === 'completed').length)
const activeTodo = computed(() => {
  return (
    props.todos.find((todo) => todo.status === 'in_progress') ||
    props.todos.find((todo) => todo.status === 'pending') ||
    props.todos[0] ||
    null
  )
})

function todoMark(status: string): string {
  if (status === 'completed') return '✓'
  if (status === 'in_progress') return '◉'
  if (status === 'cancelled') return '×'
  return '•'
}
</script>

<style scoped>
.todo-dock {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface-2);
}

.todo-header {
  width: 100%;
  border: none;
  background: transparent;
  padding: 0.55rem 0.65rem;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  cursor: pointer;
}

.todo-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text);
}

.todo-preview {
  flex: 1;
  min-width: 0;
  font-size: 0.76rem;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.todo-toggle {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.todo-list {
  max-height: 170px;
  overflow-y: auto;
  padding: 0 0.65rem 0.55rem 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.todo-item {
  font-size: 0.8rem;
  display: flex;
  gap: 0.35rem;
  color: var(--color-text-secondary);
}

.todo-item[data-active='true'] {
  color: var(--color-text);
}

.todo-item[data-status='completed'],
.todo-item[data-status='cancelled'] {
  text-decoration: line-through;
  opacity: 0.8;
}
</style>
