import { computed, ref } from 'vue'
import { api, apiUrl } from '@/api/client'
import type {
  BookChat,
  BookInfo,
  ChapterBrief,
  ChapterDetail,
  ChatMessage,
  IngestResult,
} from '@/types/api'

/** 书库 / 阅读 / 问答工作区状态。 */
export function useNovelWorkspace() {
  const books = ref<BookInfo[]>([])
  const chapters = ref<ChapterBrief[]>([])
  const currentBookId = ref('')
  const currentChapterIndex = ref(0)
  const chapter = ref<ChapterDetail | null>(null)
  const messages = ref<ChatMessage[]>([])
  const input = ref('')
  const uploading = ref(false)
  const removing = ref(false)
  const asking = ref(false)
  const clearingChat = ref(false)
  const status = ref('')
  let askAbort: AbortController | null = null

  const currentBook = computed(
    () => books.value.find((b) => b.id === currentBookId.value) ?? null,
  )
  const canPrev = computed(() => currentChapterIndex.value > 0)
  const canNext = computed(
    () =>
      chapters.value.length > 0 &&
      currentChapterIndex.value < chapters.value.length - 1,
  )

  async function loadChat(bookId: string) {
    const res = await api(`/api/v1/books/${bookId}/chat`)
    const data = (await res.json()) as BookChat & { code?: number }
    messages.value = (data.messages || []).map((m) => ({
      role: m.role as ChatMessage['role'],
      content: m.content,
      sources: m.sources || [],
    }))
  }

  async function loadBooks() {
    const res = await api('/api/v1/books')
    const data = (await res.json()) as { books: BookInfo[] }
    books.value = data.books || []
    if (!currentBookId.value && books.value.length) {
      await selectBook(books.value[0].id)
    }
  }

  async function selectBook(bookId: string) {
    currentBookId.value = bookId
    messages.value = []
    try {
      await loadChat(bookId)
    } catch (err) {
      status.value = `加载问答记录失败：${err instanceof Error ? err.message : String(err)}`
    }
    const res = await api(`/api/v1/books/${bookId}/chapters`)
    const data = (await res.json()) as { chapters: ChapterBrief[] }
    chapters.value = data.chapters || []
    if (chapters.value.length) {
      const saved =
        books.value.find((b) => b.id === bookId)?.last_chapter_index ?? 0
      const exists = chapters.value.some((c) => c.chapter_index === saved)
      const target = exists ? saved : chapters.value[0].chapter_index
      await openChapter(target)
    } else {
      chapter.value = null
    }
  }

  async function openChapter(index: number) {
    if (!currentBookId.value) return
    currentChapterIndex.value = index
    const res = await api(
      `/api/v1/books/${currentBookId.value}/chapters/${index}`,
    )
    const data = (await res.json()) as { chapter: ChapterDetail }
    chapter.value = data.chapter
    // 同步本地书单进度，换书时无需再拉列表
    const book = books.value.find((b) => b.id === currentBookId.value)
    if (book) {
      book.last_chapter_index = index
      book.last_read_at = new Date().toISOString()
    }
  }

  async function prevChapter() {
    if (canPrev.value) await openChapter(currentChapterIndex.value - 1)
  }

  async function nextChapter() {
    if (canNext.value) await openChapter(currentChapterIndex.value + 1)
  }

  async function uploadNovel(file: File) {
    uploading.value = true
    status.value = '正在解析并建立索引，长篇小说可能需要几分钟…'
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api('/api/v1/books/upload', { method: 'POST', body: fd })
      const data = (await res.json()) as { data: IngestResult }
      const info = data.data
      status.value = `导入完成：《${info.title}》· ${info.chapter_count} 章 · ${info.chunk_count} 片段`
      if (info.warning) status.value += `（${info.warning}）`
      await loadBooks()
      await selectBook(info.book_id)
    } catch (err) {
      status.value = `导入失败：${err instanceof Error ? err.message : String(err)}`
    } finally {
      uploading.value = false
    }
  }

  function onFileChange(e: Event) {
    const target = e.target as HTMLInputElement
    const file = target.files?.[0]
    if (file) void uploadNovel(file)
    target.value = ''
  }

  async function removeBook(bookId: string) {
    const target = books.value.find((b) => b.id === bookId)
    const title = target?.title || '这本书'
    if (!window.confirm(`确定删除《${title}》？\n将同时清除向量索引与问答记录，且不可恢复。`)) {
      return
    }

    removing.value = true
    status.value = `正在删除《${title}》…`
    try {
      await api(`/api/v1/books/${bookId}`, { method: 'DELETE' })
      const wasCurrent = currentBookId.value === bookId
      books.value = books.value.filter((b) => b.id !== bookId)
      status.value = `已删除《${title}》`

      if (wasCurrent) {
        currentBookId.value = ''
        chapters.value = []
        chapter.value = null
        messages.value = []
        currentChapterIndex.value = 0
        if (books.value.length) {
          await selectBook(books.value[0].id)
        }
      }
    } catch (err) {
      status.value = `删除失败：${err instanceof Error ? err.message : String(err)}`
    } finally {
      removing.value = false
    }
  }

  async function clearChat() {
    if (!currentBookId.value || clearingChat.value || asking.value) return
    if (!window.confirm('清空当前书的全部问答记录？')) return

    clearingChat.value = true
    try {
      await api(`/api/v1/books/${currentBookId.value}/chat`, { method: 'DELETE' })
      messages.value = []
    } catch (err) {
      status.value = `清空失败：${err instanceof Error ? err.message : String(err)}`
    } finally {
      clearingChat.value = false
    }
  }

  async function ask() {
    const q = input.value.trim()
    if (!q || !currentBookId.value || asking.value) return

    asking.value = true
    messages.value.push({ role: 'user', content: q })
    input.value = ''
    messages.value.push({
      role: 'assistant',
      content: '',
      sources: [],
      status: '正在检索原文…',
    })

    const history = messages.value
      .slice(0, -2)
      .map((m) => ({ role: m.role, content: m.content }))

    askAbort = new AbortController()
    try {
      const res = await fetch(apiUrl('/api/v1/chat/stream'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: askAbort.signal,
        body: JSON.stringify({
          book_id: currentBookId.value,
          question: q,
          history,
          chapter_index: chapter.value ? currentChapterIndex.value : null,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      if (!res.body) throw new Error('无响应流')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const assistant = messages.value[messages.value.length - 1]

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            const evt = JSON.parse(raw) as {
              type: string
              content?: string
              items?: ChatMessage['sources']
              sources?: ChatMessage['sources']
            }
            if (evt.type === 'status') {
              assistant.status = evt.content || ''
            } else if (evt.type === 'token') {
              assistant.status = ''
              assistant.content += evt.content || ''
            } else if (evt.type === 'sources' || evt.type === 'done') {
              const next = evt.items || evt.sources
              if (next?.length) assistant.sources = next
              if (evt.type === 'done') assistant.status = ''
            } else if (evt.type === 'error') {
              assistant.status = ''
              assistant.content += `\n[错误] ${evt.content}`
            }
          } catch {
            // ignore malformed SSE chunk
          }
        }
      }
      if (!assistant.content) assistant.content = '（没有返回内容）'
      assistant.status = ''
    } catch (err) {
      const assistant = messages.value[messages.value.length - 1]
      const aborted =
        (err instanceof DOMException && err.name === 'AbortError') ||
        askAbort?.signal.aborted
      if (assistant) {
        assistant.status = ''
        if (aborted) {
          if (!assistant.content) assistant.content = '（已停止）'
        } else {
          assistant.content = `请求失败：${err instanceof Error ? err.message : String(err)}`
        }
      }
    } finally {
      askAbort = null
      asking.value = false
    }
  }

  function stopAsk() {
    askAbort?.abort()
  }

  function onComposerKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void ask()
    }
  }

  function bootstrap() {
    loadBooks().catch((e: unknown) => {
      status.value = `连不上后端：${e instanceof Error ? e.message : String(e)}`
    })
  }

  return {
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
    clearingChat,
    status,
    canPrev,
    canNext,
    selectBook,
    openChapter,
    prevChapter,
    nextChapter,
    onFileChange,
    removeBook,
    clearChat,
    ask,
    stopAsk,
    onComposerKeydown,
    bootstrap,
  }
}
