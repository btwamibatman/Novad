import { defineStore } from 'pinia'

import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import type { AuthSession, LoginRequest } from '@/types/auth'

type AuthStatus = 'idle' | 'checking' | 'authenticated' | 'anonymous'

interface AuthState {
  session: AuthSession | null
  status: AuthStatus
  loginMessageKey: string | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    session: null,
    status: 'idle',
    loginMessageKey: null,
  }),

  getters: {
    isAuthenticated: (state): boolean => state.session !== null,
    username: (state): string => state.session?.user.username ?? '',
  },

  actions: {
    async checkSession(): Promise<AuthSession | null> {
      this.status = 'checking'
      try {
        this.session = await authApi.me()
        this.status = 'authenticated'
        this.loginMessageKey = null
        return this.session
      } catch (error) {
        this.session = null
        this.status = 'anonymous'
        if (error instanceof ApiError && error.status === 401) {
          return null
        }
        throw error
      }
    },

    async login(payload: LoginRequest): Promise<void> {
      this.status = 'checking'
      this.loginMessageKey = null
      try {
        this.session = await authApi.login(payload)
        this.status = 'authenticated'
      } catch (error) {
        this.session = null
        this.status = 'anonymous'
        throw error
      }
    },

    async logout(): Promise<void> {
      try {
        await authApi.logout()
      } finally {
        this.clear()
      }
    },

    expire(): void {
      this.session = null
      this.status = 'anonymous'
      this.loginMessageKey = 'auth.session_expired'
    },

    clear(): void {
      this.session = null
      this.status = 'anonymous'
      this.loginMessageKey = null
    },
  },
})
