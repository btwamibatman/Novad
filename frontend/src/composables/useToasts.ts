import { readonly, ref } from 'vue'

export type ToastType = 'info' | 'success' | 'error'

export interface ToastMessage {
  id: number
  message: string
  type: ToastType
}

const toasts = ref<ToastMessage[]>([])
let nextId = 1

export function useToasts() {
  function remove(id: number): void {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  function show(message: string, type: ToastType = 'info', timeout = 3200): void {
    const id = nextId++
    toasts.value.push({ id, message, type })
    window.setTimeout(() => remove(id), timeout)
  }

  return {
    toasts: readonly(toasts),
    show,
    remove,
  }
}
