<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import AIChatWindow from '@/components/chat/AIChatWindow.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useDocumentPolling } from '@/composables/useDocumentPolling'
import AppHeader from './AppHeader.vue'

const { handle } = useApiErrorHandler()
const route = useRoute()
const documentsPage = computed(() => route.name === 'documents')

useDocumentPolling((error) => handle(error))
</script>

<template>
  <div class="shell">
    <AppHeader />
    <RouterView />
  </div>

  <AIChatWindow v-if="documentsPage" />
</template>
