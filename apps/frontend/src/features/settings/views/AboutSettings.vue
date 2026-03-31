<template>
  <div class="about-settings">
    <div class="about-container">
      <div class="app-logo">
        <div class="logo-icon"><Brain :size="64" /></div>
        <h1>DawnChat</h1>
        <p class="version">v1.0.0</p>
      </div>
      
      <div class="about-section">
        <h2>{{ t.aboutPage.title }}</h2>
        <p>
          {{ t.aboutPage.description }}
        </p>
      </div>
      
      <div class="about-section">
        <h2>{{ t.aboutPage.features.title }}</h2>
        <ul>
          <li><Lock :size="16" class="mr-1 inline-icon" /> <strong>{{ t.aboutPage.features.local }}</strong></li>
          <li><Bot :size="16" class="mr-1 inline-icon" /> <strong>{{ t.aboutPage.features.models }}</strong></li>
          <li><Drama :size="16" class="mr-1 inline-icon" /> <strong>{{ t.aboutPage.features.agents }}</strong></li>
          <li><Wrench :size="16" class="mr-1 inline-icon" /> <strong>{{ t.aboutPage.features.mcp }}</strong></li>
          <li><BookOpen :size="16" class="mr-1 inline-icon" /> <strong>{{ t.aboutPage.features.knowledge }}</strong></li>
        </ul>
      </div>
      
      <div class="about-section">
        <h2>{{ t.aboutPage.techStack.title }}</h2>
        <div class="tech-stack">
          <div class="tech-item">
            <strong>{{ t.aboutPage.techStack.frontend }}</strong>
            <p>Vue 3 + TypeScript + Vite</p>
          </div>
          <div class="tech-item">
            <strong>{{ t.aboutPage.techStack.backend }}</strong>
            <p>Python + FastAPI</p>
          </div>
          <div class="tech-item">
            <strong>{{ t.aboutPage.techStack.desktop }}</strong>
            <p>Tauri 2</p>
          </div>
          <div class="tech-item">
            <strong>{{ t.aboutPage.techStack.aiEngine }}</strong>
            <p>Ollama + LiteLLM</p>
          </div>
        </div>
      </div>
      
      <div class="about-section">
        <h2>{{ t.aboutPage.license.title }}</h2>
        <p>{{ t.aboutPage.license.content }}</p>
      </div>
      
      <div class="about-footer">
        <a href="https://github.com/yourusername/dawnchat" target="_blank" class="link-btn ui-btn ui-btn--neutral">
          {{ t.aboutPage.links.github }}
        </a>
        <a href="https://dawnchat.dev" target="_blank" class="link-btn ui-btn ui-btn--neutral">
          {{ t.aboutPage.links.website }}
        </a>
        <a href="https://docs.dawnchat.dev" target="_blank" class="link-btn ui-btn ui-btn--neutral">
          {{ t.aboutPage.links.docs }}
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Brain, Lock, Bot, Drama, Wrench, BookOpen } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'

const { t } = useI18n()
</script>

<style scoped>
.about-settings {
  height: 100%;
  overflow-y: auto;
  padding: 2rem;
}

.about-container {
  max-width: 800px;
  margin: 0 auto;
}

.app-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 3rem;
}

.logo-img {
  width: 64px;
  height: 64px;
  margin-bottom: 1rem;
}

.app-logo h1 {
  margin: 0 0 0.5rem 0;
  font-size: 2.5rem;
  color: var(--color-primary);
}

.version {
  color: var(--color-text-secondary);
  font-size: 1rem;
}

.about-section {
  margin-bottom: 2.5rem;
  padding-bottom: 2.5rem;
  border-bottom: 1px solid var(--color-border);
}

.about-section:last-of-type {
  border-bottom: none;
}

.about-section h2 {
  margin: 0 0 1rem 0;
  font-size: 1.3rem;
}

.about-section p {
  line-height: 1.8;
  color: var(--color-text-secondary);
  margin: 0.5rem 0;
}

.about-section ul {
  list-style: none;
  padding: 0;
  margin: 1rem 0;
}

.about-section li {
  padding: 0.75rem 0;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.tech-stack {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1.5rem;
  margin-top: 1rem;
}

.tech-item {
  padding: 1rem;
  background: var(--color-bg-secondary);
  border-radius: 8px;
  text-align: center;
}

.tech-item strong {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--color-primary);
  font-size: 0.9rem;
}

.tech-item p {
  margin: 0;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}

.about-footer {
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin-top: 2rem;
  padding-top: 2rem;
  border-top: 1px solid var(--color-border);
}

.link-btn {
  min-height: 38px;
  padding: 0.75rem 1.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  font-weight: 600;
  transition: all 0.2s;
}

.link-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
</style>
