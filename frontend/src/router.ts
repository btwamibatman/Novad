import { createRouter, createWebHistory } from 'vue-router'

import DocumentsView from '@/views/DocumentsView.vue'
import ToolsView from '@/views/ToolsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/documents' },
    { path: '/documents', name: 'documents', component: DocumentsView },
    { path: '/tools', name: 'tools', component: ToolsView },
    { path: '/:pathMatch(.*)*', redirect: '/documents' },
  ],
})
