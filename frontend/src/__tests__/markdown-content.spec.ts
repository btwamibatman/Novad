import { mount } from '@vue/test-utils'

import MarkdownContent from '@/components/common/MarkdownContent.vue'

describe('MarkdownContent', () => {
  it('renders markdown', () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: '**Safe summary**' },
    })

    expect(wrapper.html()).toContain('<strong>Safe summary</strong>')
  })

  it('removes executable HTML', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: '<img src=x onerror="window.compromised=true"><script>alert(1)</script>',
      },
    })

    expect(wrapper.html()).not.toContain('onerror')
    expect(wrapper.html()).not.toContain('<script')
  })
})
