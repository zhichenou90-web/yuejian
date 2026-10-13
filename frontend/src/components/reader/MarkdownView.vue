<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = defineProps<{
  content: string
}>()

marked.setOptions({
  gfm: true,
  breaks: true,
})

const html = computed(() => {
  const raw = props.content || ''
  const parsed = marked.parse(raw, { async: false }) as string
  return DOMPurify.sanitize(parsed, {
    USE_PROFILES: { html: true },
  })
})
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md {
  font-size: 0.9rem;
  line-height: 1.65;
  word-break: break-word;
  color: inherit;
}

.md :deep(p) {
  margin: 0 0 0.65em;
}

.md :deep(p:last-child) {
  margin-bottom: 0;
}

.md :deep(strong) {
  color: var(--ink);
  font-weight: 700;
}

.md :deep(ul),
.md :deep(ol) {
  margin: 0.35em 0 0.7em;
  padding-left: 1.25em;
}

.md :deep(li) {
  margin: 0.2em 0;
}

.md :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.35em 0 0.35em 0.75em;
  border-left: 3px solid var(--proof);
  color: var(--ink);
  background: color-mix(in srgb, var(--wash) 28%, transparent);
}

.md :deep(code) {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.86em;
  padding: 0.1em 0.35em;
  background: color-mix(in srgb, var(--line) 45%, #fff);
}

.md :deep(pre) {
  margin: 0.5em 0;
  padding: 0.65em 0.75em;
  overflow: auto;
  background: color-mix(in srgb, var(--line) 35%, #fff);
  border: 1px solid var(--line);
}

.md :deep(pre code) {
  padding: 0;
  background: transparent;
}

.md :deep(h1),
.md :deep(h2),
.md :deep(h3),
.md :deep(h4) {
  margin: 0.75em 0 0.35em;
  font-family: var(--display-font);
  font-weight: 400;
  letter-spacing: 0.04em;
  color: var(--ink);
  font-size: 1.02em;
}

.md :deep(hr) {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 0.8em 0;
}

.md :deep(a) {
  color: var(--spine);
}
</style>
