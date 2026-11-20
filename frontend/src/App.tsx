import { useEffect, useState } from 'react'
import {
  ApiError,
  authApi,
  clearTokens,
  readTokens,
} from './api'
import type { UserProfile } from './api'
import AuthDialog from './components/AuthDialog'
import CatalogPage, { FavoritesPage } from './components/CatalogPage'
import ChatPage from './components/ChatPage'
import DealsPage from './components/DealsPage'
import AdminDisputesPage from './components/AdminDisputesPage'
import MyListingsPage from './components/MyListingsPage'
import ProfileDialog from './components/ProfileDialog'
import './App.css'

type AppView = 'catalog' | 'favorites' | 'my-listings' | 'deals' | 'messages' | 'admin-disputes'
type DealsTab = 'purchases' | 'sales' | 'offers'

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
  const [user, setUser] = useState<UserProfile | null>(null)
  const [view, setView] = useState<AppView>('catalog')
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null)
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [dealsTab, setDealsTab] = useState<DealsTab>('purchases')
  const [isCheckingSession, setIsCheckingSession] = useState(() => Boolean(readTokens()))
  const [isAuthDialogOpen, setIsAuthDialogOpen] = useState(false)
  const [isProfileDialogOpen, setIsProfileDialogOpen] = useState(false)
  const [sessionMessage, setSessionMessage] = useState<string | null>(null)

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
            setSessionMessage('Сессия завершена. Войдите в аккаунт снова.')
          } else {
            setSessionMessage(getErrorMessage(error))
          }
        }
      })
      .finally(() => {
        if (active) {
          setIsCheckingSession(false)
        }
      })

    return () => {
      active = false
    }
  }, [])

  function handleAuthenticated(profile: UserProfile) {
    setUser(profile)
    setSessionMessage(null)
    setIsAuthDialogOpen(false)
  }

  function handleDealCreated(dealId: string) {
    setSelectedDealId(dealId)
    setDealsTab('purchases')
    setView('deals')
  }

  function handleConversationOpened(conversationId: string) {
    setSelectedConversationId(conversationId)
    setView('messages')
  }

  function handleOpenOffers() {
    setDealsTab('offers')
    setView('deals')
  }

  async function handleLogout() {
    const tokens = readTokens()
    setSessionMessage(null)
    try {
      if (tokens) {
        await authApi.logout(tokens.refresh_token)
      }
    } catch (error) {
      setSessionMessage(
        `Вы вышли на этом устройстве, но сервер не подтвердил завершение сессии: ${getErrorMessage(error)}`,
      )
    } finally {
      clearTokens()
      setUser(null)
      setView('catalog')
      setSelectedDealId(null)
      setSelectedConversationId(null)
    }
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

        <nav className="site-nav" aria-label="Основная навигация">
          <button
            type="button"
            className={view === 'catalog' ? 'site-nav-active' : ''}
            aria-current={view === 'catalog' ? 'page' : undefined}
            onClick={() => setView('catalog')}
          >
            Каталог
          </button>
          <button
            type="button"
            className={view === 'favorites' ? 'site-nav-active' : ''}
            aria-current={view === 'favorites' ? 'page' : undefined}
            onClick={() => setView('favorites')}
          >
            Избранное
          </button>
          {user && !isCheckingSession && (
            <button
              type="button"
              className={view === 'my-listings' ? 'site-nav-active' : ''}
              aria-current={view === 'my-listings' ? 'page' : undefined}
              onClick={() => setView('my-listings')}
            >
              <span className="site-nav-long-label">Мои объявления</span>
              <span className="site-nav-short-label">Мои</span>
            </button>
          )}
          {user && !isCheckingSession && (
            <>
              <button
                type="button"
                className={view === 'deals' ? 'site-nav-active' : ''}
                aria-current={view === 'deals' ? 'page' : undefined}
                onClick={() => {
                  setDealsTab('purchases')
                  setView('deals')
                }}
              >
                Сделки
              </button>
              <button
                type="button"
                className={view === 'messages' ? 'site-nav-active' : ''}
                aria-current={view === 'messages' ? 'page' : undefined}
                onClick={() => setView('messages')}
              >
                Сообщения
              </button>
              {user.role === 'ADMIN' && (
                <button
                  type="button"
                  className={view === 'admin-disputes' ? 'site-nav-active' : ''}
                  aria-current={view === 'admin-disputes' ? 'page' : undefined}
                  onClick={() => setView('admin-disputes')}
                >
                  Споры
                </button>
              )}
            </>
          )}
        </nav>

        <div className="header-account">
          {isCheckingSession ? (
            <span className="session-loading" role="status">Проверяем вход...</span>
          ) : user ? (
            <>
              <button
                type="button"
                className="account-name"
                aria-label="Открыть профиль"
                onClick={() => setIsProfileDialogOpen(true)}
              >
                <span className="account-name-full">{user.display_name}</span>
                <span className="account-name-short" aria-hidden="true">{user.display_name.slice(0, 1)}</span>
              </button>
              <button className="header-button header-button-secondary" type="button" onClick={handleLogout}>
                Выйти
              </button>
            </>
          ) : (
            <button
              className="header-button"
              type="button"
              onClick={() => setIsAuthDialogOpen(true)}
            >
              Войти
              <span aria-hidden="true">↗</span>
            </button>
          )}
        </div>
      </header>

      {sessionMessage && (
        <div className="session-alert" role="alert">
          <span>{sessionMessage}</span>
          {!user && (
            <button type="button" onClick={() => setIsAuthDialogOpen(true)}>
              Войти
            </button>
          )}
        </div>
      )}

      <main id={view}>
        {view === 'catalog' ? (
          <CatalogPage
            user={user}
            onRequestAuth={() => setIsAuthDialogOpen(true)}
            onDealCreated={handleDealCreated}
            onOpenConversation={handleConversationOpened}
            onOpenOffers={handleOpenOffers}
          />
        ) : view === 'favorites' ? (
          <FavoritesPage
            user={user}
            onRequestAuth={() => setIsAuthDialogOpen(true)}
            onViewCatalog={() => setView('catalog')}
          />
        ) : view === 'my-listings' ? (
          <MyListingsPage
            user={user}
            onRequestAuth={() => setIsAuthDialogOpen(true)}
          />
        ) : view === 'deals' && user ? (
          <DealsPage
            user={user}
            initialDealId={selectedDealId}
            initialTab={dealsTab}
          />
        ) : view === 'messages' && user ? (
          <ChatPage
            user={user}
            initialConversationId={selectedConversationId}
          />
        ) : view === 'admin-disputes' && user?.role === 'ADMIN' ? (
          <AdminDisputesPage />
        ) : null}
      </main>

      <footer id="about" className="site-footer">
        <a
          className="footer-brand"
          href="#catalog"
          onClick={(event) => {
            event.preventDefault()
            setView('catalog')
          }}
        >
          БрикМаркет
        </a>
        <span>Для больших и маленьких коллекций</span>
        <span className="footer-demo">Демонстрационная версия - реальные платежи не выполняются</span>
      </footer>

      {isAuthDialogOpen && (
        <AuthDialog
          onAuthenticated={handleAuthenticated}
          onClose={() => setIsAuthDialogOpen(false)}
        />
      )}
      {isProfileDialogOpen && user && (
        <ProfileDialog
          user={user}
          onUpdated={setUser}
          onClose={() => setIsProfileDialogOpen(false)}
        />
      )}
    </div>
  )
}

export default App
