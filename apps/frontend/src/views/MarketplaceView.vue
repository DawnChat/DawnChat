<template>
  <div class="marketplace-view">
    <div class="view-header">
      <h1 class="view-title">{{ t.marketplace.title }}</h1>
      <p class="view-subtitle">{{ t.marketplace.subtitle }}</p>
    </div>

    <div class="placeholder-content">
      <div class="placeholder-card">
        <div class="placeholder-icon">
          <Bot :size="48" />
        </div>
        <h2>{{ t.marketplace.agents }}</h2>
        <p>{{ t.marketplace.viewAgents }}</p>
      </div>

      <div class="placeholder-card">
        <div class="placeholder-icon">
          <Wrench :size="48" />
        </div>
        <h2>{{ t.marketplace.tools }}</h2>
        <p>{{ t.marketplace.viewTools }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Placeholder view for marketplace
import { Bot, Wrench } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'

const { t } = useI18n()
</script>

<style scoped>
.marketplace-view {
  max-width: 80ch;
  margin: 0 auto;
}

.view-header {
  margin-bottom: 3rem;
}

.view-title {
  font-size: 2.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 0.5rem 0;
}

.view-subtitle {
  font-size: 1.125rem;
  color: var(--color-text-secondary);
  margin: 0;
}

.placeholder-content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
}

.placeholder-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  padding: 2rem;
  text-align: center;
  transition: all 0.15s ease-in-out;
}

.placeholder-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-4px);
}

.placeholder-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.placeholder-card h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 0.5rem 0;
}

.placeholder-card p {
  font-size: 1rem;
  color: var(--color-text-secondary);
  margin: 0;
}
</style>

