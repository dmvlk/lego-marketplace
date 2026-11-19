import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  authApi,
  clearTokens,
  readTokens,
  saveTokens,
} from './api'
import type { UserProfile } from './api'
import './App.css'

type AuthMode = 'login' | 'register'

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Не удалось связаться с сервером. Проверьте подключение и адрес API.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.'
}

function App() {
  const [mode, setMode] = useState<AuthMode>('login')
  const [user, setUser] = useState<UserProfile | null>(null)
  const [isLoading, setIsLoading] = useState(() => Boolean(readTokens()))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')

  useEffect(() => {
    let active = true

    if (!readTokens()) {
      return () => {
        active = false
      }
    }

    authApi
      .getProfile()
      .then((profile) => {
        if (active) {
          setUser(profile)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          if (error instanceof ApiError && error.status === 401) {
            clearTokens()
          }
          setErrorMessage(getErrorMessage(error))
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })

    return () => {
      active = false
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
      setUser(await authApi.getProfile())
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
      setUser(await authApi.getProfile())
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLogout() {
    const tokens = readTokens()
    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      if (tokens) {
        await authApi.logout(tokens.refresh_token)
      }
    } catch (error) {
      setErrorMessage(`Сеанс завершён на этом устройстве, но сервер не подтвердил выход: ${getErrorMessage(error)}`)
    } finally {
      clearTokens()
      setUser(null)
      setPassword('')
      setIsSubmitting(false)
    }
  }

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode)
    setErrorMessage(null)
    setPassword('')
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="БрикМаркет - главная">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-copy">
            <strong>БрикМаркет</strong>
            <small>маркетплейс LEGO</small>
          </span>
        </a>
        <span className="header-note">Место, где находят недостающие детали</span>
      </header>

      <main className="main-layout">
        <section className="hero-panel" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="eyebrow-dot" />
              ДЛЯ ТЕХ, КТО СОБИРАЕТ
            </p>
            <h1 id="hero-title">
              Найдите свой
              <br />
              <span>следующий набор</span>
            </h1>
            <p className="hero-description">
              Покупайте и продавайте наборы, минифигурки и детали в одном
              сообществе коллекционеров.
            </p>
          </div>

          <div className="brick-scene" aria-hidden="true">
            <div className="scene-sun" />
            <div className="floating-label label-top">СОБИРАЙ</div>
            <div className="floating-label label-bottom">ОБМЕНИВАЙСЯ</div>
            <div className="brick brick-red">
              <i />
              <i />
              <i />
            </div>
            <div className="brick brick-yellow">
              <i />
              <i />
              <i />
            </div>
            <div className="brick brick-blue">
              <i />
              <i />
            </div>
            <div className="scene-shadow" />
          </div>

          <div className="benefit-row">
            <div className="benefit">
              <span className="benefit-number">01</span>
              <span>Объявления от коллекционеров</span>
            </div>
            <div className="benefit">
              <span className="benefit-number">02</span>
              <span>Общение и сделки в одном месте</span>
            </div>
          </div>
        </section>

        <section className="auth-column" aria-label="Личный кабинет">
          {isLoading ? (
            <div className="auth-card loading-card" role="status">
              <span className="loading-indicator" />
              <p>Проверяем вход...</p>
            </div>
          ) : user ? (
            <div className="auth-card account-card">
              <div className="card-kicker">
                <span className="card-kicker-icon">✓</span>
                Личный кабинет
              </div>
              <h2>С возвращением, {user.display_name}</h2>
              <p className="card-description">
                Вы вошли в аккаунт БрикМаркет.
              </p>

              <dl className="profile-details">
                <div>
                  <dt>Email</dt>
                  <dd>{user.email}</dd>
                </div>
                <div>
                  <dt>Статус аккаунта</dt>
                  <dd>{user.status === 'ACTIVE' ? 'Активен' : user.status}</dd>
                </div>
              </dl>

              {errorMessage && (
                <p className="form-message form-message-error" role="alert">
                  {errorMessage}
                </p>
              )}

              <button
                className="primary-button"
                type="button"
                onClick={handleLogout}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Завершаем сеанс...' : 'Выйти из аккаунта'}
                <span aria-hidden="true">↗</span>
              </button>
              <p className="form-footnote">
                Ваши данные доступны только после авторизации.
              </p>
            </div>
          ) : (
            <div className="auth-card">
              <div className="card-kicker">
                <span className="card-kicker-icon">✳</span>
                Личный кабинет
              </div>
              <h2>{mode === 'login' ? 'Снова рады видеть!' : 'Создайте аккаунт'}</h2>
              <p className="card-description">
                {mode === 'login'
                  ? 'Войдите, чтобы продолжить собирать.'
                  : 'Зарегистрируйтесь и найдите то, чего не хватало коллекции.'}
              </p>

              <div className="mode-switch" role="group" aria-label="Вход или регистрация">
                <button
                  type="button"
                  aria-pressed={mode === 'login'}
                  className={mode === 'login' ? 'mode-tab active' : 'mode-tab'}
                  onClick={() => changeMode('login')}
                >
                  Войти
                </button>
                <button
                  type="button"
                  aria-pressed={mode === 'register'}
                  className={mode === 'register' ? 'mode-tab active' : 'mode-tab'}
                  onClick={() => changeMode('register')}
                >
                  Регистрация
                </button>
              </div>

              <form className="auth-form" onSubmit={handleSubmit}>
                {mode === 'register' && (
                  <label className="field">
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

                <label className="field">
                  <span>Email</span>
                  <input
                    autoComplete="email"
                    name="email"
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    required
                    type="email"
                    value={email}
                  />
                </label>

                <label className="field">
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
                    <small className="field-hint">Минимум 8 символов</small>
                  )}
                </label>

                {errorMessage && (
                  <p className="form-message form-message-error" role="alert">
                    {errorMessage}
                  </p>
                )}

                <button className="primary-button" type="submit" disabled={isSubmitting}>
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
                  className="text-button retry-button"
                  type="button"
                  onClick={handleRetrySession}
                  disabled={isSubmitting}
                >
                  Повторить проверку сессии
                </button>
              )}

              <p className="form-footnote">
                Пароль хранится в защищённом виде и не отображается в профиле.
              </p>
            </div>
          )}

          <p className="demo-note">
            <span aria-hidden="true">●</span>
            Демонстрационная версия. Реальные платежи не выполняются.
          </p>
        </section>
      </main>

      <footer className="site-footer">
        <span>БрикМаркет</span>
        <span>Для больших и маленьких коллекций</span>
      </footer>
    </div>
  )
}

export default App
