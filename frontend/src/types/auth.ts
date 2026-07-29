export interface AuthUser {
  id: number
  username: string
}

export interface AuthSession {
  session_id: string
  expires_at: string
  user: AuthUser
}

export interface LoginRequest {
  username: string
  password: string
}
