<template>
  <div class="msg-item-row assistant question-row">
    <span class="msg-role">{{ agentLabel }}</span>
    <div class="msg-item question-item">
      <div class="question-title">{{ questionRequiredLabel }}</div>
      <div v-for="(info, qIndex) in question.questions" :key="`${question.id}_${qIndex}`" class="question-block">
        <div class="question-header">{{ info.header || `${questionLabel} ${qIndex + 1}` }}</div>
        <p class="question-text">{{ info.question }}</p>
        <div class="question-options">
          <button
            v-for="option in info.options"
            :key="`${question.id}_${qIndex}_${option.label}`"
            class="question-option-btn"
            :data-picked="isQuestionOptionPicked(qIndex, option.label)"
            @click="toggleQuestionOption(qIndex, option.label, info.multiple === true)"
          >
            <span>{{ option.label }}</span>
            <small v-if="option.description">{{ option.description }}</small>
          </button>
        </div>
        <label v-if="info.custom !== false" class="question-custom">
          <span>{{ customAnswerLabel }}</span>
          <input :value="getQuestionCustomInput(qIndex)" type="text" @input="handleQuestionCustomInput(qIndex, $event)" />
        </label>
      </div>
      <div class="question-actions">
        <button class="permission-btn" @click="emit('question-reply', question.id, buildQuestionAnswers())">
          {{ submitLabel }}
        </button>
        <button class="permission-btn danger" @click="emit('question-reject', question.id)">
          {{ rejectLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface QuestionOptionLite {
  label: string
  description: string
}

interface QuestionInfoLite {
  question: string
  header: string
  options: QuestionOptionLite[]
  multiple?: boolean
  custom?: boolean
}

interface QuestionCardLite {
  id: string
  questions: QuestionInfoLite[]
}

const props = defineProps<{
  question: QuestionCardLite
  agentLabel: string
  questionRequiredLabel: string
  questionLabel: string
  customAnswerLabel: string
  submitLabel: string
  rejectLabel: string
}>()

const emit = defineEmits<{
  'question-reply': [requestID: string, answers: string[][]]
  'question-reject': [requestID: string]
}>()

const selectedByQuestion = ref<Record<number, string[]>>({})
const customByQuestion = ref<Record<number, string>>({})

const isQuestionOptionPicked = (questionIndex: number, label: string) => {
  return Boolean(selectedByQuestion.value[questionIndex]?.includes(label))
}

const toggleQuestionOption = (questionIndex: number, label: string, multiple: boolean) => {
  const current = selectedByQuestion.value[questionIndex] || []
  if (!multiple) {
    selectedByQuestion.value[questionIndex] = current[0] === label ? [] : [label]
    return
  }
  if (current.includes(label)) {
    selectedByQuestion.value[questionIndex] = current.filter((item) => item !== label)
    return
  }
  selectedByQuestion.value[questionIndex] = [...current, label]
}

const getQuestionCustomInput = (questionIndex: number) => {
  return customByQuestion.value[questionIndex] || ''
}

const handleQuestionCustomInput = (questionIndex: number, event: Event) => {
  customByQuestion.value[questionIndex] = (event.target as HTMLInputElement | null)?.value || ''
}

const buildQuestionAnswers = (): string[][] => {
  return props.question.questions.map((info, index) => {
    const selected = [...(selectedByQuestion.value[index] || [])]
    const custom = String(customByQuestion.value[index] || '').trim()
    if (info.custom !== false && custom) {
      if (info.multiple === true) {
        if (!selected.includes(custom)) selected.push(custom)
      } else {
        return [custom]
      }
    }
    if (info.multiple !== true && selected.length > 1) {
      return [selected[0]]
    }
    return selected
  })
}
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

.question-row .msg-item {
  width: min(640px, 92%);
}

.question-item {
  background: var(--color-surface-2);
}

.question-title {
  font-size: 0.82rem;
  font-weight: 600;
}

.question-block {
  margin-top: 0.6rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--color-border);
}

.question-header {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.question-text {
  margin: 0.2rem 0 0.4rem 0;
  font-size: 0.84rem;
  white-space: pre-wrap;
}

.question-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.question-option-btn {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface-3);
  padding: 0.3rem 0.45rem;
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  cursor: pointer;
  color: var(--color-text);
}

.question-option-btn small {
  color: var(--color-text-secondary);
}

.question-option-btn[data-picked='true'] {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-3));
}

.question-custom {
  margin-top: 0.45rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.question-custom input {
  height: 30px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface-3);
  color: var(--color-text);
  padding: 0 0.5rem;
}

.question-actions {
  margin-top: 0.6rem;
  display: flex;
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
</style>

