import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  authApi,
  readTokens,
  saveTokens,
} from '../api'
import type { UserProfile } from '../api'
import './AuthDialog.css'

type AuthMode = 'login' | 'register'

interface AuthDialogProps {
  onAuthenticated: (profile: UserProfile) => void
  onClose: () => void
}

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Не удалось связаться с сервером. Проверьте подключение и адрес API.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.'
}

export default function AuthDialog({
  onAuthenticated,
  onClose,
}: AuthDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [mode, setMode] = useState<AuthMode>('login')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => {
      if (dialog?.open) {
        dialog.close()
      }
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      const tokens =
        mode === 'register'
          ? await authApi.register({ email, password, display_name: displayName })
          : await authApi.login({ email, password })

      saveTokens(tokens)
      onAuthenticated(await authApi.getProfile())
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleRetrySession() {
    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      onAuthenticated(await authApi.getProfile())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setErrorMessage('Сессия завершена. Войдите в аккаунт снова.')
      } else {
        setErrorMessage(getErrorMessage(error))
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode)
    setErrorMessage(null)
    setPassword('')
  }

  return (
    <dialog
      ref={dialogRef}
      className="auth-dialog"
      aria-labelledby="auth-dialog-title"
      onCancel={onClose}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault()
          onClose()
        }
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="auth-dialog-card">
        <button
          className="dialog-close"
          type="button"
          aria-label="Закрыть окно"
          onClick={onClose}
        >
          ×
        </button>
        <div className="dialog-brand-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <p className="dialog-eyebrow">ЛИЧНЫЙ КАБИНЕТ</p>
        <h2 id="auth-dialog-title">
          {mode === 'login' ? 'Снова рады видеть!' : 'Создайте аккаунт'}
        </h2>
        <p className="dialog-description">
          {mode === 'login'
            ? 'Войдите, чтобы продолжить собирать.'
            : 'Зарегистрируйтесь и найдите то, чего не хватало коллекции.'}
        </p>

        <div className="auth-dialog-switch" role="group" aria-label="Вход или регистрация">
          <button
            type="button"
            aria-pressed={mode === 'login'}
            className={mode === 'login' ? 'auth-dialog-tab active' : 'auth-dialog-tab'}
            onClick={() => changeMode('login')}
          >
            Войти
          </button>
          <button
            type="button"
            aria-pressed={mode === 'register'}
            className={mode === 'register' ? 'auth-dialog-tab active' : 'auth-dialog-tab'}
            onClick={() => changeMode('register')}
          >
            Регистрация
          </button>
        </div>

        <form className="auth-dialog-form" onSubmit={handleSubmit}>
          {mode === 'register' && (
            <label className="auth-dialog-field">
              <span>Как к вам обращаться</span>
              <input
                autoComplete="name"
                maxLength={100}
                minLength={2}
                name="display_name"
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Например, Дмитрий"
                required
                value={displayName}
              />
            </label>
          )}

          <label className="auth-dialog-field">
            <span>Email</span>
            <input
              autoComplete="email"
              autoFocus
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              required
              type="email"
              value={email}
            />
          </label>

          <label className="auth-dialog-field">
            <span>Пароль</span>
            <input
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={8}
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Не менее 8 символов"
              required
              type="password"
              value={password}
            />
            {mode === 'register' && (
              <small>Минимум 8 символов</small>
            )}
          </label>

          {errorMessage && (
            <p className="auth-dialog-error" role="alert">
              {errorMessage}
            </p>
          )}

          <button className="auth-dialog-submit" type="submit" disabled={isSubmitting}>
            {isSubmitting
              ? 'Подождите...'
              : mode === 'login'
                ? 'Войти в аккаунт'
                : 'Создать аккаунт'}
            {!isSubmitting && <span aria-hidden="true">↗</span>}
          </button>
        </form>

        {readTokens() && (
          <button
            className="auth-dialog-retry"
            type="button"
            onClick={handleRetrySession}
            disabled={isSubmitting}
          >
            Повторить проверку сессии
          </button>
        )}

        <p className="auth-dialog-footnote">
          Пароль хранится в защищённом виде и не отображается в профиле.
        </p>
      </div>
    </dialog>
  )
}
