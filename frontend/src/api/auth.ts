import { requestJson } from './client'
import type { AuthSession, LoginRequest } from '@/types/auth'

export const authApi = {
  login(payload: LoginRequest): Promise<AuthSession> {
    return requestJson('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },

  me(): Promise<AuthSession> {
    return requestJson('/api/auth/me')
  },

  logout(): Promise<void> {
    return requestJson('/api/auth/logout', { method: 'POST' })
  },
}
