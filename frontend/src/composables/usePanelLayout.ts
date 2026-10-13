import { onMounted, onUnmounted, ref, type Ref } from 'vue'

const STORAGE_KEY = 'novel-rag-panel-widths'

/** 各栏最小宽度（px） */
export const PANEL_MIN = {
  spine: 52,
  left: 200,
  mid: 320,
  right: 280,
} as const

const LEFT_DEFAULT = 250
const RIGHT_DEFAULT = 340
const LEFT_MAX = 480
const RIGHT_MAX = 560
const HANDLE = 6

function loadSaved(): { left: number; right: number } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { left: LEFT_DEFAULT, right: RIGHT_DEFAULT }
    const parsed = JSON.parse(raw) as { left?: number; right?: number }
    return {
      left: typeof parsed.left === 'number' ? parsed.left : LEFT_DEFAULT,
      right: typeof parsed.right === 'number' ? parsed.right : RIGHT_DEFAULT,
    }
  } catch {
    return { left: LEFT_DEFAULT, right: RIGHT_DEFAULT }
  }
}

/**
 * 三栏可拖拽调宽：左目录 / 中正文 / 右问答。
 * 书脊宽度固定；中间栏吃剩余空间，并保证不低于 PANEL_MIN.mid。
 */
export function usePanelLayout(shellEl: Ref<HTMLElement | null>) {
  const saved = loadSaved()
  const leftWidth = ref(saved.left)
  const rightWidth = ref(saved.right)
  const dragging = ref<'left' | 'right' | null>(null)

  function shellInnerWidth(): number {
    return shellEl.value?.clientWidth ?? window.innerWidth
  }

  function clampLeft(next: number, right: number): number {
    const budget =
      shellInnerWidth() - PANEL_MIN.spine - HANDLE * 2 - right - PANEL_MIN.mid
    const max = Math.min(LEFT_MAX, Math.max(PANEL_MIN.left, budget))
    return Math.min(Math.max(next, PANEL_MIN.left), max)
  }

  function clampRight(next: number, left: number): number {
    const budget =
      shellInnerWidth() - PANEL_MIN.spine - HANDLE * 2 - left - PANEL_MIN.mid
    const max = Math.min(RIGHT_MAX, Math.max(PANEL_MIN.right, budget))
    return Math.min(Math.max(next, PANEL_MIN.right), max)
  }

  function persist() {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ left: leftWidth.value, right: rightWidth.value }),
    )
  }

  function reclampAll() {
    leftWidth.value = clampLeft(leftWidth.value, rightWidth.value)
    rightWidth.value = clampRight(rightWidth.value, leftWidth.value)
  }

  function startDrag(side: 'left' | 'right', e: PointerEvent) {
    e.preventDefault()
    dragging.value = side
    const startX = e.clientX
    const startLeft = leftWidth.value
    const startRight = rightWidth.value

    const target = e.currentTarget as HTMLElement
    target.setPointerCapture(e.pointerId)

    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - startX
      if (side === 'left') {
        leftWidth.value = clampLeft(startLeft + dx, rightWidth.value)
      } else {
        // 向右拖手柄 → 右侧变窄；向左拖 → 右侧变宽
        rightWidth.value = clampRight(startRight - dx, leftWidth.value)
      }
    }

    const onUp = (ev: PointerEvent) => {
      dragging.value = null
      target.releasePointerCapture(ev.pointerId)
      target.removeEventListener('pointermove', onMove)
      target.removeEventListener('pointerup', onUp)
      target.removeEventListener('pointercancel', onUp)
      persist()
    }

    target.addEventListener('pointermove', onMove)
    target.addEventListener('pointerup', onUp)
    target.addEventListener('pointercancel', onUp)
  }

  function onResize() {
    reclampAll()
  }

  onMounted(() => {
    reclampAll()
    window.addEventListener('resize', onResize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', onResize)
  })

  return {
    leftWidth,
    rightWidth,
    dragging,
    startDrag,
    PANEL_MIN,
    HANDLE,
  }
}
