import { readStoredValue, writeStoredValue } from '@/utils/storage'

describe('storage utilities', () => {
  it('reads and writes values when storage is available', () => {
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    }

    expect(writeStoredValue('theme', 'light', storage)).toBe(true)
    expect(readStoredValue('theme', storage)).toBe('light')
    expect(readStoredValue('missing', storage)).toBeNull()
  })

  it('falls back when browser storage access is blocked', () => {
    const blockedStorage = {
      getItem: () => { throw new DOMException('Access denied', 'SecurityError') },
      setItem: () => { throw new DOMException('Access denied', 'SecurityError') },
    }

    expect(readStoredValue('theme', blockedStorage)).toBeNull()
    expect(writeStoredValue('theme', 'dark', blockedStorage)).toBe(false)
  })

  it('allows preferences to initialize when local storage is blocked', async () => {
    vi.resetModules()
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Access denied', 'SecurityError')
    })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Access denied', 'SecurityError')
    })

    await expect(import('@/composables/usePreferences')).resolves.toHaveProperty('usePreferences')
    expect(document.documentElement.dataset.theme).toBe('dark')

    getItem.mockRestore()
    setItem.mockRestore()
  })
})
