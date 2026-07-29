<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const props = defineProps<{
  content: string
}>()

const sanitizedHtml = computed(() => {
  const unsafeHtml = marked.parse(props.content || '', { async: false })
  return DOMPurify.sanitize(unsafeHtml)
})
</script>

<template>
  <!-- Sanitization is deliberately centralized in this component. -->
  <div class="preview" v-html="sanitizedHtml"></div>
</template>
