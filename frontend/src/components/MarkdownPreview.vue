<script setup lang="ts">
import { computed } from "vue";
import { renderMarkdown } from "../markdown";

const props = defineProps<{ content: string }>();
const html = computed(() => renderMarkdown(props.content));
</script>

<template>
  <!-- HTML is filtered by the allowlist in renderMarkdown before insertion. -->
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div class="markdown-preview" v-html="html"></div>
</template>

<style scoped>
.markdown-preview {
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  line-height: 1.7;
  overflow-wrap: anywhere;
  white-space: normal;
  color: #334155;
}
.markdown-preview :deep(p) {
  margin: 0.65em 0;
  white-space: normal;
}
.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3),
.markdown-preview :deep(h4),
.markdown-preview :deep(h5),
.markdown-preview :deep(h6) {
  margin: 1em 0 0.5em;
  line-height: 1.4;
  font-weight: 650;
  color: #172b4d;
}
.markdown-preview :deep(h1) {
  font-size: 1.35em;
}
.markdown-preview :deep(h2) {
  font-size: 1.2em;
}
.markdown-preview :deep(h3),
.markdown-preview :deep(h4),
.markdown-preview :deep(h5),
.markdown-preview :deep(h6) {
  font-size: 1.05em;
}
.markdown-preview :deep(ul),
.markdown-preview :deep(ol) {
  padding-left: 1.6em;
  margin: 0.65em 0;
}
.markdown-preview :deep(li) {
  margin: 0.3em 0;
}
.markdown-preview :deep(a) {
  color: #2563eb;
  text-decoration: underline;
}
.markdown-preview :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.88em;
  background: #eef2f7;
  padding: 0.15em 0.3em;
  border-radius: 4px;
}
.markdown-preview :deep(pre) {
  padding: 12px;
  border-radius: 8px;
  background: #f1f5f9;
  max-height: 320px;
  overflow: auto;
  white-space: pre;
  overflow-wrap: normal;
}
.markdown-preview :deep(pre code) {
  padding: 0;
  background: none;
}
.markdown-preview :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.8em 0;
  font-size: 0.92em;
}
.markdown-preview :deep(th),
.markdown-preview :deep(td) {
  border: 1px solid #dce3ed;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  min-width: 80px;
}
.markdown-preview :deep(th) {
  background: #edf3fb;
  font-weight: 600;
}
.markdown-preview :deep(tr:nth-child(even)) {
  background: #f8fafc;
}
.markdown-preview :deep(blockquote) {
  margin: 0.8em 0;
  padding: 2px 12px;
  border-left: 3px solid #9bb5e5;
  background: #f5f8fd;
  color: #64748b;
}
.markdown-preview :deep(hr) {
  border: 0;
  border-top: 1px solid #e2e8f0;
}
</style>
