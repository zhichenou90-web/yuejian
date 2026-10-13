<script setup lang="ts">
import { nextTick, useTemplateRef, watch } from 'vue'
import { SUGGESTED_QUESTIONS } from '@/brand'
import type { BookInfo, ChatMessage } from '@/types/api'
import MarkdownView from '@/components/reader/MarkdownView.vue'

const props = defineProps<{
  currentBook: BookInfo | null
  messages: ChatMessage[]
  input: string
  asking: boolean
  clearingChat?: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  'update:input': [value: string]
  ask: []
  stop: []
  clearChat: []
  keydown: [e: KeyboardEvent]
  openChapter: [index: number]
  suggest: [question: string]
}>()

const messagesEl = useTemplateRef<HTMLElement>('messagesEl')
/** 用户上翻看旧消息时不强制滚底；贴底或新提问时再跟随。 */
let stickToBottom = true

function onThreadScroll() {
  const el = messagesEl.value
  if (!el) return
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom = gap < 96
}

watch(
  () => props.messages.map((m) => `${m.status || ''}\0${m.content}`).join('\0'),
  async () => {
    await nextTick()
    const el = messagesEl.value
    if (!el || !stickToBottom) return
    el.scrollTop = el.scrollHeight
  },
)

watch(
  () => props.messages.length,
  (n, prev) => {
    if (n > (prev ?? 0)) stickToBottom = true
  },
)
</script>

<template>
  <aside class="chat">
    <header class="chat__head">
      <div class="chat__head-row">
        <div class="chat__head-text">
          <p class="chat__eyebrow">问答</p>
          <h3 class="chat__title">向本书提问</h3>
        </div>
        <button
          type="button"
          class="chat__clear"
          :disabled="disabled || asking || clearingChat || !messages.length"
          title="清空本会话"
          @click="emit('clearChat')"
        >
          {{ clearingChat ? '清空中…' : '清空会话' }}
        </button>
      </div>
      <p class="chat__book">
        <template v-if="currentBook">
          当前：《{{ currentBook.title }}》
        </template>
        <template v-else>先在左侧导入并选中一本书</template>
      </p>
    </header>

    <div ref="messagesEl" class="chat__thread" @scroll="onThreadScroll">
      <div v-if="!messages.length" class="chat__empty">
        <p class="chat__empty-title">
          {{ disabled ? '选中书籍后即可提问' : '可以从这些问题开始' }}
        </p>
        <p class="chat__empty-copy">
          回答会依据检索到的原文片段，并附上可点击的出处章节。
        </p>
        <div v-if="!disabled" class="chat__chips">
          <button
            v-for="q in SUGGESTED_QUESTIONS"
            :key="q"
            type="button"
            class="chat__chip"
            :disabled="asking"
            @click="emit('suggest', q)"
          >
            {{ q }}
          </button>
        </div>
      </div>

      <div
        v-for="(m, i) in messages"
        :key="i"
        class="chat__note"
        :class="m.role"
      >
        <span class="chat__role">{{ m.role === 'user' ? '问' : '答' }}</span>
        <div class="chat__text">
          <p
            v-if="m.role === 'assistant' && !m.content && m.status"
            class="chat__status"
          >
            {{ m.status }}
          </p>
          <MarkdownView v-else-if="m.role === 'assistant'" :content="m.content" />
          <template v-else>{{ m.content }}</template>
          <div
            v-if="m.role === 'assistant' && m.content && m.sources?.length"
            class="chat__sources"
          >
            <span class="chat__sources-label">出处</span>
            <button
              v-for="s in m.sources"
              :key="`${s.chapter_index}-${s.chapter_title}`"
              type="button"
              class="chat__source"
              :title="s.excerpt || s.chapter_title"
              @click="emit('openChapter', s.chapter_index)"
            >
              {{ s.chapter_title }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="chat__composer">
      <label class="chat__label" for="chat-input">输入问题</label>
      <textarea
        id="chat-input"
        :value="input"
        :disabled="disabled || asking"
        placeholder="人物关系、情节因果、某一章发生了什么…"
        @input="emit('update:input', ($event.target as HTMLTextAreaElement).value)"
        @keydown="emit('keydown', $event)"
      />
      <div class="chat__row">
        <span class="chat__hint">
          {{
            asking
              ? '生成中，可随时停止'
              : '全书可问 · 「这一章」限当前章 · Enter 发送'
          }}
        </span>
        <button
          v-if="asking"
          type="button"
          class="chat__send chat__send--stop"
          @click="emit('stop')"
        >
          停止
        </button>
        <button
          v-else
          type="button"
          class="chat__send"
          :disabled="disabled || !input.trim()"
          @click="emit('ask')"
        >
          发送
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100%;
  background: var(--panel);
  border-left: 1px solid var(--line);
  box-shadow: -12px 0 24px rgba(21, 32, 40, 0.06);
  overflow: hidden;
}

.chat__head {
  padding: 16px 18px 14px;
  border-bottom: 1px solid var(--line);
  border-top: 3px solid var(--accent);
}

.chat__head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.chat__head-text {
  min-width: 0;
}

.chat__clear {
  flex-shrink: 0;
  margin-top: 2px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: transparent;
  color: var(--ink-soft);
  padding: 4px 10px;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: color 0.15s var(--ease), border-color 0.15s var(--ease);
}

.chat__clear:hover:not(:disabled) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.chat__clear:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chat__eyebrow {
  margin: 0;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-weight: 600;
}

.chat__title {
  margin: 4px 0 0;
  font-family: var(--display-font);
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.chat__book {
  margin: 6px 0 0;
  font-size: 0.8rem;
  color: var(--ink-soft);
}

.chat__thread {
  flex: 1;
  overflow: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chat__empty {
  padding: 8px 0 4px;
}

.chat__empty-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--ink);
}

.chat__empty-copy {
  margin: 8px 0 0;
  font-size: 0.82rem;
  line-height: 1.55;
  color: var(--ink-soft);
}

.chat__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.chat__chip {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--spine);
  padding: 6px 12px;
  font-size: 0.78rem;
  cursor: pointer;
  transition: border-color 0.15s var(--ease), background 0.15s var(--ease);
}

.chat__chip:hover:not(:disabled) {
  border-color: var(--spine);
  background: color-mix(in srgb, var(--wash) 40%, #fff);
}

.chat__chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chat__note {
  display: grid;
  grid-template-columns: 1.5rem 1fr;
  gap: 10px;
  align-items: start;
  animation: note-in 0.35s var(--ease) both;
}

.chat__role {
  width: 1.5rem;
  height: 1.5rem;
  display: grid;
  place-items: center;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0;
  border: 1px solid currentColor;
  border-radius: 4px;
}

.chat__note.user .chat__role {
  color: var(--accent);
}

.chat__note.assistant .chat__role {
  color: var(--spine);
}

.chat__text {
  font-size: 0.9rem;
  line-height: 1.6;
  padding-top: 1px;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.chat__note.user .chat__text {
  color: var(--ink);
  white-space: pre-wrap;
}

.chat__note.assistant .chat__text {
  color: var(--ink-soft);
  white-space: normal;
}

.chat__sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
}

.chat__sources-label {
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  color: var(--ink-soft);
  margin-right: 2px;
}

.chat__source {
  border: 1px solid var(--line);
  border-radius: 4px;
  background: color-mix(in srgb, var(--wash) 35%, #fff);
  color: var(--spine);
  padding: 3px 8px;
  font-size: 0.72rem;
  line-height: 1.4;
  letter-spacing: 0.02em;
  cursor: pointer;
  text-align: left;
}

.chat__source:hover {
  border-color: var(--spine);
}

.chat__composer {
  border-top: 1px solid var(--line);
  padding: 12px 14px 14px;
  display: grid;
  gap: 8px;
  background: color-mix(in srgb, var(--panel) 80%, #fff);
}

.chat__label {
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  color: var(--ink-soft);
}

.chat__composer textarea {
  width: 100%;
  min-height: 84px;
  resize: vertical;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--ink);
  padding: 10px 12px;
  line-height: 1.5;
}

.chat__composer textarea:focus {
  border-color: var(--spine);
  outline: none;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--wash) 70%, transparent);
}

.chat__row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.chat__hint {
  font-size: 0.72rem;
  color: var(--ink-soft);
}

.chat__send {
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff7f7;
  padding: 8px 16px;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: background 0.15s var(--ease);
}

.chat__send:hover:not(:disabled) {
  background: var(--accent-deep);
}

.chat__send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chat__send--stop {
  background: transparent;
  color: var(--accent);
}

.chat__send--stop:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 8%, #fff);
}

.chat__status {
  margin: 0;
  color: var(--ink-soft);
  font-size: 0.84rem;
  letter-spacing: 0.04em;
}

@keyframes note-in {
  from {
    opacity: 0;
    transform: translateX(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
</style>
