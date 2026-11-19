const API_BASE_URL = (
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/+$/, '')
const SESSION_STORAGE_KEY = 'brick-marketplace-session'

export interface SessionTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserProfile {
  id: string
  email: string
  display_name: string
  avatar_reference: string | null
  status: string
  role: string
  created_at: string
}

interface RegisterPayload {
  email: string
  password: string
  display_name: string
}

interface LoginPayload {
  email: string
  password: string
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

export function readTokens(): SessionTokens | null {
  const stored = sessionStorage.getItem(SESSION_STORAGE_KEY)
  if (!stored) {
    return null
  }

  try {
    const parsed: unknown = JSON.parse(stored)
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'access_token' in parsed &&
      typeof parsed.access_token === 'string' &&
      'refresh_token' in parsed &&
      typeof parsed.refresh_token === 'string' &&
      'token_type' in parsed &&
      typeof parsed.token_type === 'string'
    ) {
      return {
        access_token: parsed.access_token,
        refresh_token: parsed.refresh_token,
        token_type: parsed.token_type,
      }
    }
  } catch {
    sessionStorage.removeItem(SESSION_STORAGE_KEY)
    return null
  }

  sessionStorage.removeItem(SESSION_STORAGE_KEY)
  return null
}

export function saveTokens(tokens: SessionTokens): void {
  sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(tokens))
}

export function clearTokens(): void {
  sessionStorage.removeItem(SESSION_STORAGE_KEY)
}

function parseSessionTokens(value: unknown): SessionTokens {
  if (
    typeof value === 'object' &&
    value !== null &&
    'access_token' in value &&
    typeof value.access_token === 'string' &&
    'refresh_token' in value &&
    typeof value.refresh_token === 'string' &&
    'token_type' in value &&
    typeof value.token_type === 'string'
  ) {
    return {
      access_token: value.access_token,
      refresh_token: value.refresh_token,
      token_type: value.token_type,
    }
  }
  throw new ApiError('Сервер вернул некорректный ответ авторизации.', 502)
}

let refreshInProgress: Promise<void> | null = null

async function responseError(response: Response): Promise<ApiError> {
  const body = await response.text()
  if (!body) {
    return new ApiError(`Ошибка запроса (${response.status})`, response.status)
  }

  let payload: unknown
  try {
    payload = JSON.parse(body)
  } catch {
    return new ApiError(body, response.status)
  }

  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail: unknown = payload.detail
    if (typeof detail === 'string') {
      return new ApiError(detail, response.status)
    }
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item: unknown) => {
          if (typeof item === 'object' && item !== null && 'msg' in item) {
            return String(item.msg)
          }
          return ''
        })
        .filter(Boolean)
      if (messages.length > 0) {
        return new ApiError(messages.join('. '), response.status)
      }
    }
  }

  return new ApiError(`Ошибка запроса (${response.status})`, response.status)
}

async function send(
  path: string,
  init: RequestInit,
  authenticated: boolean,
): Promise<Response> {
  const makeRequest = () => {
    const headers = new Headers(init.headers)
    const tokens = authenticated ? readTokens() : null
    if (tokens) {
      headers.set('Authorization', `Bearer ${tokens.access_token}`)
    }
    if (init.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    return fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  }

  let response = await makeRequest()
  if (authenticated && response.status === 401 && path !== '/auth/refresh') {
    await refreshSession()
    response = await makeRequest()
    if (response.status === 401) {
      clearTokens()
    }
  }

  if (!response.ok) {
    throw await responseError(response)
  }
  return response
}

async function refreshSession(): Promise<void> {
  if (!refreshInProgress) {
    refreshInProgress = (async () => {
      const tokens = readTokens()
      if (!tokens) {
        throw new ApiError('Сессия завершена. Войдите в аккаунт снова.', 401)
      }

      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      })
      if (!response.ok) {
        const error = await responseError(response)
        if (response.status === 401) {
          clearTokens()
        }
        throw error
      }

      saveTokens(parseSessionTokens(await response.json()))
    })().finally(() => {
      refreshInProgress = null
    })
  }
  return refreshInProgress
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  authenticated = false,
): Promise<T> {
  const response = await send(path, init, authenticated)
  return (await response.json()) as T
}

export const authApi = {
  async register(payload: RegisterPayload): Promise<SessionTokens> {
    return parseSessionTokens(
      await requestJson<unknown>(
        '/auth/register',
        { method: 'POST', body: JSON.stringify(payload) },
      ),
    )
  },
  async login(payload: LoginPayload): Promise<SessionTokens> {
    return parseSessionTokens(
      await requestJson<unknown>(
        '/auth/login',
        { method: 'POST', body: JSON.stringify(payload) },
      ),
    )
  },
  async getProfile(): Promise<UserProfile> {
    return requestJson('/users/me', { method: 'GET' }, true)
  },
  async logout(refreshToken: string): Promise<void> {
    await send(
      '/auth/logout',
      {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
      false,
    )
  },
}
