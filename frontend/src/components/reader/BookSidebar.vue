<script setup lang="ts">
import { APP_NAME, APP_TAGLINE } from '@/brand'
import type { BookInfo, ChapterBrief } from '@/types/api'

defineProps<{
  books: BookInfo[]
  chapters: ChapterBrief[]
  currentBookId: string
  currentChapterIndex: number
  uploading: boolean
  removing: boolean
  status: string
}>()

defineEmits<{
  selectBook: [bookId: string]
  openChapter: [index: number]
  pickFile: []
  removeBook: [bookId: string]
}>()

const statusIsError = (s: string) =>
  s.includes('失败') || s.includes('无法') || s.includes('连不上')
</script>

<template>
  <aside class="toc">
    <header class="toc__head">
      <div class="toc__brand">
        <span class="toc__mark" aria-hidden="true">笺</span>
        <div>
          <h1 class="toc__name">{{ APP_NAME }}</h1>
          <p class="toc__desc">{{ APP_TAGLINE }}</p>
        </div>
      </div>
    </header>

    <div class="toc__upload">
      <button
        type="button"
        class="toc__upload-btn"
        :disabled="uploading || removing"
        @click="$emit('pickFile')"
      >
        <span class="toc__upload-mark" aria-hidden="true">＋</span>
        {{ uploading ? '正在导入索引…' : '导入 TXT 小说' }}
      </button>
      <p class="toc__hint" :class="{ 'is-warn': statusIsError(status) }">
        {{ status || '支持「第N章」「第N回」格式 · 首次导入需建索引' }}
      </p>
    </div>

    <section class="toc__section toc__section--books">
      <h2 class="toc__label">书架</h2>
      <div class="toc__books">
        <div
          v-for="b in books"
          :key="b.id"
          class="toc__book-row"
          :class="{ 'is-active': b.id === currentBookId }"
        >
          <button
            type="button"
            class="toc__book"
            :disabled="removing"
            @click="$emit('selectBook', b.id)"
          >
            <span class="toc__book-title">{{ b.title }}</span>
            <span class="toc__book-meta">{{ b.chapter_count }} 章 · 已索引</span>
          </button>
          <button
            type="button"
            class="toc__book-del"
            title="删除书籍"
            :disabled="removing"
            @click.stop="$emit('removeBook', b.id)"
          >
            删除
          </button>
        </div>
        <p v-if="!books.length" class="toc__empty">书架还是空的，导入一本 TXT 开始。</p>
      </div>
    </section>

    <section class="toc__section toc__section--chapters">
      <div class="toc__label-row">
        <h2 class="toc__label">目录</h2>
        <span v-if="chapters.length" class="toc__count">{{ chapters.length }} 章</span>
      </div>
      <div class="toc__chapters">
        <button
          v-for="c in chapters"
          :key="c.chapter_index"
          type="button"
          class="toc__chapter"
          :class="{ 'is-active': c.chapter_index === currentChapterIndex }"
          @click="$emit('openChapter', c.chapter_index)"
        >
          <span class="toc__chapter-index">{{ String(c.chapter_index + 1).padStart(2, '0') }}</span>
          <span class="toc__chapter-title">{{ c.chapter_title }}</span>
        </button>
        <p v-if="currentBookId && !chapters.length" class="toc__empty">暂无章节</p>
        <p v-else-if="!currentBookId" class="toc__empty">选中书籍后显示目录</p>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.toc {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100%;
  background: color-mix(in srgb, var(--panel) 88%, #fff);
  border-right: 1px solid var(--line);
  overflow: hidden;
}

.toc__head {
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--line);
}

.toc__brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toc__mark {
  flex-shrink: 0;
  width: 2.4rem;
  height: 2.4rem;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--spine);
  color: var(--spine-ink);
  font-family: var(--brand-font);
  font-size: 1.15rem;
  letter-spacing: 0;
  box-shadow: var(--shadow-soft);
}

.toc__name {
  margin: 0;
  font-family: var(--brand-font);
  font-size: 1.55rem;
  font-weight: 400;
  letter-spacing: 0.1em;
  color: var(--spine);
  line-height: 1.2;
}

.toc__desc {
  margin: 4px 0 0;
  font-size: 0.78rem;
  color: var(--ink-soft);
  line-height: 1.4;
}

.toc__upload {
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}

.toc__upload-btn {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 12px;
  border: 1px solid var(--spine);
  border-radius: var(--radius-sm);
  background: var(--spine);
  color: var(--spine-ink);
  cursor: pointer;
  transition: background 0.2s var(--ease), transform 0.2s var(--ease);
}

.toc__upload-btn:hover:not(:disabled) {
  background: #1f524e;
}

.toc__upload-btn:active:not(:disabled) {
  transform: translateY(1px);
}

.toc__upload-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.toc__upload-mark {
  font-size: 1.05rem;
  line-height: 1;
}

.toc__hint {
  margin: 8px 0 0;
  font-size: 0.74rem;
  line-height: 1.45;
  color: var(--ink-soft);
}

.toc__hint.is-warn {
  color: var(--accent);
}

.toc__section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.toc__section--books {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--line);
}

.toc__section--chapters {
  flex: 1 1 auto;
  min-height: 0;
}

.toc__label-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-right: 16px;
}

.toc__label {
  margin: 0;
  padding: 12px 16px 4px;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  color: var(--ink-soft);
  font-weight: 600;
  flex: 0 0 auto;
}

.toc__count {
  font-size: 0.68rem;
  color: var(--spine-mute);
  font-variant-numeric: tabular-nums;
}

.toc__books {
  max-height: min(240px, 34vh);
  min-height: 4.5rem;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 6px 0 12px;
  overscroll-behavior: contain;
}

.toc__chapters {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 4px 0 16px;
  overscroll-behavior: contain;
}

.toc__book,
.toc__chapter {
  width: 100%;
  display: grid;
  gap: 2px;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--ink);
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s var(--ease);
  flex-shrink: 0;
}

.toc__book-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: stretch;
  min-height: 3.4rem;
}

.toc__book-row.is-active {
  background: color-mix(in srgb, var(--wash) 55%, transparent);
  box-shadow: inset 3px 0 0 var(--accent);
}

.toc__book-row:hover {
  background: color-mix(in srgb, var(--wash) 35%, transparent);
}

.toc__book-row.is-active:hover {
  background: color-mix(in srgb, var(--wash) 55%, transparent);
}

.toc__book {
  min-height: 3.4rem;
  align-content: center;
  padding-right: 8px;
}

.toc__book:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.toc__book-del {
  align-self: center;
  margin-right: 10px;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--ink-soft);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  cursor: pointer;
  opacity: 0.55;
  transition: opacity 0.15s var(--ease), color 0.15s var(--ease), border-color 0.15s var(--ease);
}

.toc__book-row:hover .toc__book-del,
.toc__book-row.is-active .toc__book-del {
  opacity: 1;
}

.toc__book-del:hover:not(:disabled) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.toc__book-del:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.toc__chapter:hover {
  background: color-mix(in srgb, var(--wash) 35%, transparent);
}

.toc__chapter.is-active {
  background: color-mix(in srgb, var(--wash) 55%, transparent);
  box-shadow: inset 3px 0 0 var(--accent);
}

.toc__book-title,
.toc__chapter-title {
  font-size: 0.9rem;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.toc__book-meta {
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--ink-soft);
}

.toc__chapter {
  grid-template-columns: 2rem 1fr;
  align-items: start;
  gap: 8px;
}

.toc__chapter-index {
  font-variant-numeric: tabular-nums;
  font-size: 0.72rem;
  color: var(--spine-mute);
  padding-top: 0.2em;
}

.toc__chapter.is-active .toc__chapter-index {
  color: var(--accent);
  font-weight: 700;
}

.toc__empty {
  margin: 0;
  padding: 8px 16px;
  font-size: 0.8rem;
  color: var(--ink-soft);
}

@media (max-width: 760px) {
  .toc {
    max-height: 48vh;
  }

  .toc__books {
    max-height: min(160px, 22vh);
  }
}
</style>
