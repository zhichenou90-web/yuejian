<script setup lang="ts">
import { computed } from 'vue'
import { APP_NAME, APP_TAGLINE } from '@/brand'
import type { ChapterDetail } from '@/types/api'

const props = defineProps<{
  chapter: ChapterDetail | null
  canPrev: boolean
  canNext: boolean
  hasBooks?: boolean
}>()

defineEmits<{
  prev: []
  next: []
  pickFile: []
}>()

const displayTitle = computed(() => props.chapter?.chapter_title ?? '')
</script>

<template>
  <main class="page">
    <template v-if="chapter">
      <header class="page__bar">
        <div class="page__heading">
          <p class="page__eyebrow">正文</p>
          <h2 class="page__title">{{ displayTitle }}</h2>
          <div class="page__rule" aria-hidden="true" />
        </div>
        <div class="page__nav">
          <button type="button" class="page__nav-btn" :disabled="!canPrev" @click="$emit('prev')">
            上一章
          </button>
          <button type="button" class="page__nav-btn" :disabled="!canNext" @click="$emit('next')">
            下一章
          </button>
        </div>
      </header>
      <div class="page__scroll">
        <article :key="chapter.chapter_index" class="page__body">
          {{ chapter.content }}
        </article>
      </div>
    </template>

    <div v-else class="page__empty">
      <p class="page__empty-brand">{{ APP_NAME }}</p>
      <h3 class="page__empty-title">
        {{ hasBooks ? '从左侧目录打开一章' : '导入小说，开始阅读' }}
      </h3>
      <p class="page__empty-copy">
        {{ APP_TAGLINE }}。左侧管理书架与目录，中间读正文，右侧向 AI 提问。
      </p>
      <ol v-if="!hasBooks" class="page__steps">
        <li>导入 TXT 小说（支持章 / 回标题）</li>
        <li>在目录中打开章节阅读</li>
        <li>在右侧提问，点击出处跳转</li>
      </ol>
      <button
        v-if="!hasBooks"
        type="button"
        class="page__cta"
        @click="$emit('pickFile')"
      >
        导入 TXT 小说
      </button>
    </div>
  </main>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.45), transparent 140px),
    var(--paper);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35);
}

.page__bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 18px clamp(14px, 4%, 36px) 14px;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--paper) 70%, #fff);
  min-width: 0;
}

.page__heading {
  min-width: 0;
  flex: 1;
}

.page__eyebrow {
  margin: 0;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  color: var(--ink-soft);
  font-weight: 600;
}

.page__title {
  margin: 6px 0 0;
  font-family: var(--display-font);
  font-size: clamp(1.05rem, 1.6vw + 0.6rem, 1.65rem);
  font-weight: 400;
  letter-spacing: 0.04em;
  line-height: 1.35;
  color: var(--ink);
  overflow-wrap: anywhere;
}

.page__rule {
  margin-top: 10px;
  width: 56px;
  height: 3px;
  border-radius: 2px;
  background: var(--accent);
}

.page__nav {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.page__nav-btn {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--ink);
  padding: 8px 14px;
  cursor: pointer;
  transition: border-color 0.15s var(--ease), color 0.15s var(--ease);
}

.page__nav-btn:hover:not(:disabled) {
  border-color: var(--spine);
  color: var(--spine);
}

.page__nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.page__scroll {
  flex: 1;
  overflow: auto;
  min-width: 0;
  padding: 40px clamp(14px, 5%, 48px) 72px;
}

.page__body {
  width: 100%;
  max-width: min(40rem, 100%);
  margin: 0 auto;
  box-sizing: border-box;
  font-family: var(--reader-font);
  font-size: clamp(0.98rem, 0.4vw + 0.9rem, 1.12rem);
  line-height: 2;
  letter-spacing: 0.02em;
  color: var(--ink);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  animation: page-in 0.45s var(--ease) both;
}

.page__empty {
  max-width: 28rem;
  margin: 16vh auto 0;
  padding: 0 24px;
  text-align: center;
}

.page__empty-brand {
  margin: 0;
  font-family: var(--brand-font);
  font-size: 1.1rem;
  letter-spacing: 0.2em;
  color: var(--spine);
}

.page__empty-title {
  margin: 14px 0 0;
  font-family: var(--display-font);
  font-size: 1.55rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--ink);
}

.page__empty-copy {
  margin: 12px 0 0;
  color: var(--ink-soft);
  line-height: 1.7;
  font-size: 0.92rem;
}

.page__steps {
  margin: 20px 0 0;
  padding: 0;
  list-style: none;
  text-align: left;
  display: grid;
  gap: 10px;
  counter-reset: step;
}

.page__steps li {
  position: relative;
  padding: 10px 14px 10px 2.4rem;
  background: color-mix(in srgb, #fff 70%, var(--panel));
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-size: 0.86rem;
  color: var(--ink);
  counter-increment: step;
}

.page__steps li::before {
  content: counter(step);
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 1.35rem;
  height: 1.35rem;
  display: grid;
  place-items: center;
  border-radius: 4px;
  background: var(--spine);
  color: var(--spine-ink);
  font-size: 0.72rem;
  font-weight: 700;
}

.page__cta {
  margin-top: 22px;
  border: 1px solid var(--spine);
  border-radius: var(--radius-sm);
  background: var(--spine);
  color: var(--spine-ink);
  padding: 11px 20px;
  cursor: pointer;
  transition: background 0.15s var(--ease);
}

.page__cta:hover {
  background: #1f524e;
}

@keyframes page-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 760px) {
  .page__bar {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px 18px 12px;
  }

  .page__scroll {
    padding: 24px 18px 48px;
  }

  .page__empty {
    margin-top: 8vh;
  }
}
</style>
