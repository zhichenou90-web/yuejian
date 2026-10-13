export interface BookInfo {
  id: string
  title: string
  filename: string
  chapter_count: number
  chunk_count: number
  split_mode: string
  warning: string
  created_at: string
  last_chapter_index: number
  last_read_at: string
}

export interface ChapterBrief {
  book_id: string
  chapter_index: number
  chapter_no: number | null
  chapter_title: string
  content_length: number
}

export interface ChapterDetail {
  book_id: string
  chapter_index: number
  chapter_no: number | null
  chapter_title: string
  content: string
}

export interface SourceRef {
  chapter_index: number
  chapter_title: string
  excerpt: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: SourceRef[]
  /** 检索/生成中的临时提示，不入库。 */
  status?: string
}

export interface StoredChatMessage extends ChatMessage {
  id: string
  created_at: string
  sources?: SourceRef[]
}

export interface BookChat {
  session_id: string | null
  messages: StoredChatMessage[]
}

export interface IngestResult {
  book_id: string
  title: string
  chapter_count: number
  chunk_count: number
  split_mode: string
  warning: string
}
