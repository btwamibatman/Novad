type ReadableStorage = Pick<Storage, 'getItem'>
type WritableStorage = Pick<Storage, 'setItem'>

export function readStoredValue(
  key: string,
  storage: ReadableStorage = localStorage,
): string | null {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

export function writeStoredValue(
  key: string,
  value: string,
  storage: WritableStorage = localStorage,
): boolean {
  try {
    storage.setItem(key, value)
    return true
  } catch {
    return false
  }
}
