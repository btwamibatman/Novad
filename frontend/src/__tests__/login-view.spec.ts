import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

import { ApiError } from '@/api/client'
import LoginView from '@/components/auth/LoginView.vue'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'

describe('login accessibility and language', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    i18n.global.locale.value = 'en'
  })

  it('reveals the password without submitting or changing its value, then hides it again', async () => {
    const authStore = useAuthStore()
    const login = vi.spyOn(authStore, 'login').mockResolvedValue()
    const wrapper = mount(LoginView, { global: { plugins: [i18n] } })

    await wrapper.get('input[name="username"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('secret')
    const toggle = wrapper.get('.password-toggle')
    expect(toggle.attributes('type')).toBe('button')
    expect(toggle.attributes('aria-controls')).toBe('login-password')

    await toggle.trigger('click')
    expect(wrapper.get('input[name="password"]').attributes('type')).toBe('text')
    expect(toggle.text()).toBe('Show password'.replace('Show', 'Hide'))
    expect((wrapper.get('input[name="password"]').element as HTMLInputElement).value).toBe('secret')
    expect(login).not.toHaveBeenCalled()

    await toggle.trigger('click')
    expect(wrapper.get('input[name="password"]').attributes('type')).toBe('password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(login).toHaveBeenCalledExactlyOnceWith({ username: 'admin', password: 'secret' })
    expect((wrapper.get('input[name="password"]').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('translates an existing credentials error and password control after language changes', async () => {
    const authStore = useAuthStore()
    vi.spyOn(authStore, 'login').mockRejectedValue(new ApiError('Unauthorized', 401, null, null))
    const wrapper = mount(LoginView, { global: { plugins: [i18n] } })

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Invalid username or password.')
    expect(wrapper.get('input[name="password"]').attributes('aria-describedby')).toBe('login-error')

    await wrapper.findAll('.language-button')[1]!.trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toBe('Неверное имя пользователя или пароль.')
    expect(wrapper.get('.password-toggle').text()).toBe('Показать пароль')
    expect(wrapper.get('.auth-eyebrow').text()).toBe('Консоль документов')
    expect(document.documentElement.lang).toBe('ru')
    wrapper.unmount()
  })

  it('announces a pending sign-in and prevents another submit', async () => {
    const authStore = useAuthStore()
    const wrapper = mount(LoginView, { global: { plugins: [i18n] } })
    authStore.status = 'checking'
    await flushPromises()

    expect(wrapper.get('form').attributes('aria-busy')).toBe('true')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').text()).toBe('Signing in…')
    wrapper.unmount()
  })
})
