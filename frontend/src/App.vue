<script setup lang="ts">
import { computed, onMounted, useTemplateRef } from 'vue'
import { APP_NAME } from '@/brand'
import BookSidebar from '@/components/reader/BookSidebar.vue'
import ChatPanel from '@/components/reader/ChatPanel.vue'
import ReaderPane from '@/components/reader/ReaderPane.vue'
import { useNovelWorkspace } from '@/composables/useNovelWorkspace'
import { PANEL_MIN, usePanelLayout } from '@/composables/usePanelLayout'

const {
  books,
  chapters,
  currentBookId,
  currentBook,
  currentChapterIndex,
  chapter,
  messages,
  input,
  uploading,
  removing,
  asking,
  status,
  canPrev,
  canNext,
  selectBook,
  openChapter,
  prevChapter,
  nextChapter,
  onFileChange,
  removeBook,
  ask,
  stopAsk,
  onComposerKeydown,
  bootstrap,
  clearChat,
  clearingChat,
} = useNovelWorkspace()

const shellEl = useTemplateRef<HTMLElement>('shellEl')
const { leftWidth, rightWidth, dragging, startDrag } = usePanelLayout(shellEl)
const fileInput = useTemplateRef<HTMLInputElement>('fileInput')

const spineLabel = computed(() => {
  if (currentBook.value) return currentBook.value.title
  return APP_NAME
})

const spineMeta = computed(() => {
  if (!currentBook.value) return '导入小说开始'
  const total = chapters.value.length || currentBook.value.chapter_count
  const n = currentChapterIndex.value + 1
  return `${n} / ${total}`
})

const shellStyle = computed(() => ({
  '--panel-spine': `${PANEL_MIN.spine}px`,
  '--panel-left': `${leftWidth.value}px`,
  '--panel-right': `${rightWidth.value}px`,
}))

function pickFile() {
  fileInput.value?.click()
}

async function askSuggested(question: string) {
  input.value = question
  await ask()
}

onMounted(() => {
  bootstrap()
})
</script>

<template>
  <div
    ref="shellEl"
    class="shell"
    :class="{ 'is-dragging': dragging }"
    :style="shellStyle"
  >
    <input
      ref="fileInput"
      type="file"
      accept=".txt"
      class="hidden-file"
      @change="onFileChange"
    />

    <aside class="spine" aria-label="当前书籍">
      <div class="spine__brand">{{ APP_NAME }}</div>
      <div class="spine__title">{{ spineLabel }}</div>
      <div class="spine__meta">{{ spineMeta }}</div>
    </aside>

    <div class="panel panel--left">
      <BookSidebar
        :books="books"
        :chapters="chapters"
        :current-book-id="currentBookId"
        :current-chapter-index="currentChapterIndex"
        :uploading="uploading"
        :removing="removing"
        :status="status"
        @select-book="selectBook"
        @open-chapter="openChapter"
        @pick-file="pickFile"
        @remove-book="removeBook"
      />
    </div>

    <div
      class="splitter"
      role="separator"
      aria-orientation="vertical"
      aria-label="调整目录栏宽度"
      tabindex="0"
      @pointerdown="startDrag('left', $event)"
    />

    <div class="panel panel--mid">
      <ReaderPane
        :chapter="chapter"
        :can-prev="canPrev"
        :can-next="canNext"
        :has-books="books.length > 0"
        @prev="prevChapter"
        @next="nextChapter"
        @pick-file="pickFile"
      />
    </div>

    <div
      class="splitter"
      role="separator"
      aria-orientation="vertical"
      aria-label="调整问答栏宽度"
      tabindex="0"
      @pointerdown="startDrag('right', $event)"
    />

    <div class="panel panel--right">
      <ChatPanel
        v-model:input="input"
        :current-book="currentBook"
        :messages="messages"
        :asking="asking"
        :clearing-chat="clearingChat"
        :disabled="!currentBookId"
        @ask="ask"
        @stop="stopAsk"
        @clear-chat="clearChat"
        @keydown="onComposerKeydown"
        @open-chapter="openChapter"
        @suggest="askSuggested"
      />
    </div>
  </div>
</template>

<style scoped>
.shell {
  --panel-spine: 52px;
  --panel-left: 250px;
  --panel-right: 340px;

  display: grid;
  grid-template-columns:
    var(--panel-spine)
    var(--panel-left)
    6px
    minmax(320px, 1fr)
    6px
    var(--panel-right);
  height: 100%;
  min-height: 100vh;
  min-width: 0;
  overflow: hidden;
  animation: shell-in 0.55s var(--ease) both;
}

.shell.is-dragging {
  cursor: col-resize;
  user-select: none;
}

.shell.is-dragging * {
  cursor: col-resize !important;
  user-select: none !important;
}

.hidden-file {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.panel {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel > :deep(*) {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.splitter {
  position: relative;
  z-index: 5;
  width: 6px;
  margin: 0 -1px;
  cursor: col-resize;
  touch-action: none;
  background: transparent;
}

.splitter::before {
  content: '';
  position: absolute;
  inset: 0 2px;
  background: var(--line);
  transition: background 0.15s var(--ease), inset 0.15s var(--ease);
}

.splitter:hover::before,
.splitter:focus-visible::before,
.shell.is-dragging .splitter::before {
  inset: 0 1px;
  background: var(--spine);
}

.splitter:focus-visible {
  outline: none;
}

.spine {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), transparent 30%),
    linear-gradient(90deg, #0f2e2c, var(--spine) 40%, #1a4a46);
  color: var(--spine-ink);
  border-right: 1px solid #0b2422;
  box-shadow: inset -8px 0 16px rgba(0, 0, 0, 0.18);
  min-width: 0;
  overflow: hidden;
}

.spine__brand {
  writing-mode: vertical-rl;
  font-family: var(--brand-font);
  font-size: 0.95rem;
  letter-spacing: 0.35em;
  color: var(--wash);
}

.spine__title {
  writing-mode: vertical-rl;
  font-family: var(--display-font);
  font-size: 1.35rem;
  letter-spacing: 0.22em;
  line-height: 1.2;
  max-height: 58vh;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spine__meta {
  writing-mode: vertical-rl;
  font-size: 0.72rem;
  letter-spacing: 0.18em;
  color: var(--spine-mute);
}

@keyframes shell-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 900px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(180px, 28vh) minmax(240px, 1fr) minmax(220px, 36vh);
  }

  .spine {
    flex-direction: row;
    justify-content: space-between;
    padding: 12px 16px;
    grid-column: 1;
  }

  .spine__brand,
  .spine__title,
  .spine__meta {
    writing-mode: horizontal-tb;
    max-height: none;
    letter-spacing: 0.08em;
  }

  .spine__title {
    font-size: 1.1rem;
    flex: 1;
    text-align: center;
    padding: 0 12px;
  }

  .panel--left {
    grid-row: 2;
  }

  .panel--mid {
    grid-row: 3;
  }

  .panel--right {
    grid-row: 4;
  }

  .splitter {
    display: none;
  }
}
</style>
