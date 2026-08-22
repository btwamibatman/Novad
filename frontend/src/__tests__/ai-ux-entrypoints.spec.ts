import { flushPromises, mount, RouterLinkStub, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

import ContentReviewPanel from '@/components/analysis/ContentReviewPanel.vue'
import LayoutReviewPanel from '@/components/analysis/LayoutReviewPanel.vue'
import SummaryPanel from '@/components/analysis/SummaryPanel.vue'
import AIChatWindow from '@/components/chat/AIChatWindow.vue'
import { i18n } from '@/i18n'
import { makeDocument } from '@/__tests__/fixtures'

const mocks = vi.hoisted(() => ({
  store: {
    selectedDocument: null as unknown,
    busy: false,
    isPending: vi.fn().mockReturnValue(false),
    summarize: vi.fn(),
    reviewContent: vi.fn(),
    reviewLayout: vi.fn(),
    load: vi.fn(),
  },
  getProviderInfo: vi.fn(),
  useDocumentChat: vi.fn(),
  handle: vi.fn(),
  show: vi.fn(),
}))

vi.mock('@/stores/documents', () => ({
  useDocumentsStore: () => mocks.store,
}))

vi.mock('@/api/ai', () => ({
  aiAnalysisApi: { getProviderInfo: mocks.getProviderInfo },
}))

vi.mock('@/composables/useDocumentChat', () => ({
  useDocumentChat: mocks.useDocumentChat,
}))

vi.mock('@/composables/useApiErrorHandler', () => ({
  useApiErrorHandler: () => ({ handle: mocks.handle }),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ show: mocks.show }),
}))

const panelGlobal = {
  plugins: [i18n],
  stubs: { RouterLink: RouterLinkStub, MarkdownContent: true },
}

describe('protected AI entry points and disclosure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    mocks.store.selectedDocument = makeDocument({ id: 33 })
    mocks.store.busy = false
    mocks.getProviderInfo.mockResolvedValue({
      provider: 'Gemini',
      model: 'gemini-test',
      service_tier: 'paid',
      max_remote_retention_hours: 48,
      requires_verified_artifact: true,
    })
  })

  it('routes Summary to the protected flow with document and task intent', () => {
    const wrapper = shallowMount(SummaryPanel, { global: panelGlobal })
    const link = wrapper.getComponent(RouterLinkStub)

    expect(link.classes()).toContain('primary')
    expect(link.props('to')).toEqual({
      name: 'tools',
      query: { task: 'summary', document_id: '33' },
    })
    expect(wrapper.text()).toContain('Quick text summary (legacy)')
    wrapper.unmount()
  })

  it('routes Content Review to the protected flow and labels extracted-text review as legacy', () => {
    const wrapper = shallowMount(ContentReviewPanel, { global: panelGlobal })
    const link = wrapper.getComponent(RouterLinkStub)

    expect(link.classes()).toContain('primary')
    expect(link.props('to')).toEqual({
      name: 'tools',
      query: { task: 'content_review', document_id: '33' },
    })
    expect(wrapper.text()).toContain('Review extracted text (legacy)')
    wrapper.unmount()
  })

  it('routes Layout Review to protected PDF and clearly labels the paid original path as legacy', async () => {
    const wrapper = shallowMount(LayoutReviewPanel, { global: panelGlobal })
    await flushPromises()
    const link = wrapper.getComponent(RouterLinkStub)

    expect(link.classes()).toContain('primary')
    expect(link.props('to')).toEqual({
      name: 'tools',
      query: { task: 'layout_review', document_id: '33' },
    })
    expect(wrapper.text()).toContain('legacy, paid tier')
    wrapper.unmount()
  })

  it('fails closed with an accurate message when Layout provider disclosure is unavailable', async () => {
    mocks.getProviderInfo.mockRejectedValue(new Error('offline'))
    const wrapper = shallowMount(LayoutReviewPanel, { global: panelGlobal })
    await flushPromises()

    expect(wrapper.text()).toContain('Provider details are unavailable')
    expect(wrapper.text()).not.toContain('blocked for unpaid Gemini')
    wrapper.unmount()
  })

  it('keeps chat grid structure intact and discloses the external provider', async () => {
    const document = makeDocument({ id: 33 })
    mocks.useDocumentChat.mockReturnValue({
      open: ref(true),
      maximized: ref(false),
      position: ref(null),
      selectedDocumentId: ref(33),
      messages: ref([]),
      asking: ref(false),
      processedDocuments: ref([document]),
      selectedDocument: ref(document),
      ask: vi.fn(),
      abortRequest: vi.fn(),
      clearSessionMessages: vi.fn(),
    })

    const wrapper = mount(AIChatWindow, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.get('.ai-chat-body').element.children).toHaveLength(3)
    expect(wrapper.text()).toContain('External provider: Gemini')
    expect(wrapper.text()).toContain('model: gemini-test')
    expect(wrapper.get('.ai-chat-context a').attributes('href')).toBe(
      'https://ai.google.dev/gemini-api/terms',
    )
    wrapper.unmount()
  })
})
