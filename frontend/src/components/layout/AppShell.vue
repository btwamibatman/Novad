<script setup lang="ts">
import { ref } from 'vue'
import { RouterView } from 'vue-router'

import AIChatWindow from '@/components/chat/AIChatWindow.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useDocumentPolling } from '@/composables/useDocumentPolling'
import AppHeader from './AppHeader.vue'

const { handle } = useApiErrorHandler()
const chatWindow = ref<InstanceType<typeof AIChatWindow> | null>(null)
const chatOpen = ref(false)

useDocumentPolling((error) => handle(error))
</script>

<template>
  <div class="shell">
    <AppHeader :chat-open="chatOpen" @toggle-chat="chatWindow?.toggleOpen()" />
    <RouterView />
  </div>

  <AIChatWindow ref="chatWindow" @update:open="chatOpen = $event" />
</template>
