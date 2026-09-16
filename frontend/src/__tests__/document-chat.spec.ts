import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

import { ApiError } from '@/api/client'
import { documentsApi } from '@/api/documents'
import AIChatWindow from '@/components/chat/AIChatWindow.vue'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'
import type { AIChatResponse } from '@/types/document'
import { makeDocument } from './fixtures'

const answer: AIChatResponse = {
  answer: 'The task is complete.', model: 'test', truncated_context: false,
  privacy_applied: false, masked_entity_count: 0,
  conclusions: [{ observation: 'The task is complete.', requires_review: false, suggestion: '',
    citations: [{ chunk_index: 0, quote: 'Completed', page: 2, text_matched: true }] }],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

async function setup() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().session = {
    session_id: 'chat-test', expires_at: '2099-01-01T00:00:00Z', user: { id: 1, username: 'test' },
  }
  const store = useDocumentsStore()
  store.documents = [makeDocument(), makeDocument({ id: 2, filename: 'second.pdf' })]
  const wrapper = mount(AIChatWindow, { global: { plugins: [pinia, i18n] } })
  await wrapper.get('.ai-chat-toggle').trigger('click')
  return { wrapper, store }
}

describe('document chat requests', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })
  afterEach(() => { vi.useRealTimers() })

  it('shows processing and elapsed time, prevents duplicate sends, then displays cited evidence', async () => {
    vi.useFakeTimers()
    const intervals = vi.spyOn(globalThis, 'setInterval')
    const clearInterval = vi.spyOn(globalThis, 'clearInterval')
    const pending = deferred<AIChatResponse>()
    const ask = vi.spyOn(documentsApi, 'ask').mockReturnValue(pending.promise)
    const { wrapper } = await setup()
    await wrapper.get('textarea').setValue('  How well was the task done?  ')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('[role="status"]').text()).toContain('Processing your request')
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    expect(ask).toHaveBeenCalledWith(1, { question: 'How well was the task done?', history: [], mode: 'question' }, expect.any(AbortSignal))
    await vi.advanceTimersByTimeAsync(21000)
    expect(wrapper.get('[role="status"]').text()).toContain('Elapsed: 21 sec.')
    expect(wrapper.text()).toContain('This is taking longer')
    await wrapper.get('form').trigger('submit')
    expect(ask).toHaveBeenCalledTimes(1)
    pending.resolve(answer)
    await flushPromises()
    expect(wrapper.text()).toContain('Answer ready')
    expect(wrapper.get('blockquote').text()).toContain('Completed')
    expect(wrapper.find('.chat-spinner').exists()).toBe(false)
    wrapper.unmount()
    expect(clearInterval).toHaveBeenCalledWith(intervals.mock.results[0]!.value)
  })

  it('keeps a server error visible and retries the same question without duplicating history', async () => {
    const ask = vi.spyOn(documentsApi, 'ask')
      .mockRejectedValueOnce(new ApiError('Local AI timed out.', 503, null, null))
      .mockResolvedValueOnce(answer)
    const { wrapper } = await setup()
    await wrapper.get('textarea').setValue('Evaluate the task')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Local AI timed out.')
    expect(wrapper.findAll('.ai-chat-message.user')).toHaveLength(1)
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(ask.mock.calls[1]?.[1]).toEqual(ask.mock.calls[0]?.[1])
    expect(wrapper.findAll('.ai-chat-message.user')).toHaveLength(1)
    expect(wrapper.findAll('.ai-chat-message.assistant')).toHaveLength(1)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each([
    [new TypeError('Failed to fetch'), 'Check your connection'],
    [new ApiError('Too many requests', 429, null, '30'), '30'],
  ])('explains network and rate-limit errors: %s', async (error, expected) => {
    vi.spyOn(documentsApi, 'ask').mockRejectedValue(error)
    const { wrapper } = await setup()
    await wrapper.get('textarea').setValue('Question')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain(expected)
    wrapper.unmount()
  })

  it('ignores a late response after switching documents and aborts on unmount', async () => {
    const first = deferred<AIChatResponse>()
    const second = deferred<AIChatResponse>()
    const ask = vi.spyOn(documentsApi, 'ask').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { wrapper } = await setup()
    await wrapper.get('textarea').setValue('First question')
    await wrapper.get('form').trigger('submit')
    const firstSignal = ask.mock.calls[0]![2]
    await wrapper.get('.ai-chat-context select').setValue('2')
    expect(firstSignal.aborted).toBe(true)
    await wrapper.get('textarea').setValue('Second question')
    await wrapper.get('form').trigger('submit')
    first.resolve(answer)
    await flushPromises()
    expect(wrapper.find('.ai-chat-message.assistant').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('Processing')
    wrapper.unmount()
    expect(ask.mock.calls[1]![2].aborted).toBe(true)
    second.resolve(answer)
    await flushPromises()
    expect(sessionStorage.getItem('document-console-chat:chat-test:2')).toBeNull()
  })

  it('does not send blank questions or requests without a processed document', async () => {
    const ask = vi.spyOn(documentsApi, 'ask')
    const { wrapper, store } = await setup()
    await wrapper.get('textarea').setValue('   ')
    await wrapper.get('form').trigger('submit')
    store.documents = []
    await flushPromises()
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    expect(ask).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
