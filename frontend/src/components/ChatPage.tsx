import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  catalogApi,
  chatApi,
  getWebSocketUrl,
  readTokens,
} from '../api'
import type { ChatMessage, Conversation, UserProfile } from '../api'
import './ChatPage.css'

interface ChatPageProps {
  user: UserProfile
  initialConversationId: string | null
}

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Не удалось связаться с сервером. Проверьте подключение и адрес API.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Не удалось загрузить сообщения. Попробуйте ещё раз.'
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

function parseMessageEvent(value: unknown): ChatMessage | null {
  if (typeof value !== 'object' || value === null || !('type' in value) || !('message' in value)) {
    return null
  }
  if (value.type !== 'message' || typeof value.message !== 'object' || value.message === null) {
    return null
  }
  const message = value.message
  if (
    !('id' in message) || typeof message.id !== 'string' ||
    !('conversation_id' in message) || typeof message.conversation_id !== 'string' ||
    !('sender_id' in message) || typeof message.sender_id !== 'string' ||
    !('content' in message) || typeof message.content !== 'string' ||
    !('created_at' in message) || typeof message.created_at !== 'string'
  ) {
    return null
  }
  return {
    id: message.id,
    conversation_id: message.conversation_id,
    sender_id: message.sender_id,
    content: message.content,
    created_at: message.created_at,
  }
}

export default function ChatPage({ user, initialConversationId }: ChatPageProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [listingTitles, setListingTitles] = useState<Record<string, string>>({})
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(
    initialConversationId,
  )
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const [realtimeState, setRealtimeState] = useState<{
    conversationId: string | null
    connected: boolean
  }>({ conversationId: null, connected: false })
  const messageCount = useRef(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const isRealtime = realtimeState.conversationId === selectedConversationId &&
    realtimeState.connected
  const visibleMessages = messages.filter(
    (message) => message.conversation_id === selectedConversationId,
  )

  useEffect(() => {
    let active = true
    async function loadConversations() {
      try {
        const items = await chatApi.listConversations()
        if (!active) return
        setConversations(items)
        const ids = [...new Set(items.map((item) => item.listing_id))]
        const pairs = await Promise.all(ids.map(async (listingId) => {
          try {
            const listing = await catalogApi.getListing(listingId)
            return [listingId, listing.title] as const
          } catch (loadError) {
            if (isNotFound(loadError)) {
              return [listingId, 'Объявление больше недоступно'] as const
            }
            throw loadError
          }
        }))
        if (active) {
          setListingTitles(Object.fromEntries(pairs))
          setError(null)
          setIsLoading(false)
        }
      } catch (loadError) {
        if (active) {
          setError(getErrorMessage(loadError))
          setIsLoading(false)
        }
      }
    }
    void loadConversations()
    const interval = window.setInterval(() => {
      void chatApi.listConversations()
        .then((items) => {
          if (active) setConversations(items)
        })
        .catch((loadError: unknown) => {
          if (active) setError(getErrorMessage(loadError))
        })
    }, 15000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [user.id])

  useEffect(() => {
    let active = true
    const conversationId = selectedConversationId
    messageCount.current = 0
    if (!conversationId) {
      return () => {
        active = false
      }
    }
    const activeConversationId = conversationId

    async function loadMessages() {
      try {
        let page = Math.floor(messageCount.current / 100) + 1
        let loaded: ChatMessage[] = []
        let batch: ChatMessage[]
        do {
          batch = await chatApi.listMessages(activeConversationId, page)
          loaded = loaded.concat(batch)
          page += 1
        } while (active && batch.length === 100)

        if (active && loaded.length > 0) {
          setMessages((current) => {
            const knownIds = new Set(current.map((message) => message.id))
            const additions = loaded.filter((message) => !knownIds.has(message.id))
            messageCount.current += additions.length
            return [...current, ...additions].sort((a, b) =>
              a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
            )
          })
          setError(null)
        }
      } catch (loadError) {
        if (active) setError(getErrorMessage(loadError))
      }
    }

    void loadMessages()
    const interval = window.setInterval(() => void loadMessages(), 5000)
    const tokens = readTokens()
    let socket: WebSocket | null = null
    if (tokens) {
      try {
        socket = new WebSocket(getWebSocketUrl(`/ws/conversations/${activeConversationId}`))
        socket.onopen = () => {
          socket?.send(JSON.stringify({ access_token: tokens.access_token }))
          setRealtimeState({ conversationId: activeConversationId, connected: true })
        }
        socket.onmessage = (event) => {
          try {
            const message = parseMessageEvent(JSON.parse(String(event.data)))
            if (!message) return
            setMessages((current) => {
              if (current.some((item) => item.id === message.id)) return current
              messageCount.current += 1
              return [...current, message].sort((a, b) =>
                a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
              )
            })
            setRealtimeState({ conversationId: activeConversationId, connected: true })
          } catch {
            setError('Получено некорректное сообщение чата.')
          }
        }
        socket.onerror = () => setRealtimeState({ conversationId: activeConversationId, connected: false })
        socket.onclose = () => setRealtimeState({ conversationId: activeConversationId, connected: false })
      } catch {
        window.setTimeout(() => {
          if (active) {
            setRealtimeState({ conversationId: activeConversationId, connected: false })
            setError('Не удалось подключить обновления чата в реальном времени.')
          }
        }, 0)
      }
    }

    return () => {
      active = false
      window.clearInterval(interval)
      socket?.close()
    }
  }, [selectedConversationId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [visibleMessages])

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedConversationId || !draft.trim() || isSending) return
    setIsSending(true)
    setError(null)
    try {
      const message = await chatApi.sendMessage(selectedConversationId, draft.trim())
      setMessages((current) => {
        if (current.some((item) => item.id === message.id)) return current
        messageCount.current += 1
        return [...current, message]
      })
      setDraft('')
    } catch (sendError) {
      setError(getErrorMessage(sendError))
    } finally {
      setIsSending(false)
    }
  }

  const selectedConversation = conversations.find(
    (conversation) => conversation.id === selectedConversationId,
  )

  return (
    <section className="chat-page" aria-labelledby="chat-title">
      <header className="chat-page-heading">
        <div>
          <p className="chat-eyebrow">ЛИЧНЫЕ СООБЩЕНИЯ</p>
          <h1 id="chat-title">Диалоги <span>коллекционеров</span></h1>
          <p>Обсуждайте детали объявления и договаривайтесь о покупке.</p>
        </div>
        <span className={isRealtime ? 'chat-connection chat-connection-live' : 'chat-connection'}>
          {isRealtime ? 'На связи' : 'Обновление сообщений'}
        </span>
      </header>

      {error && <div className="chat-alert" role="alert">{error}</div>}

      <div className="chat-layout">
        <aside className="chat-conversation-list" aria-label="Список диалогов">
          {isLoading ? (
            <div className="chat-empty">Загружаем диалоги...</div>
          ) : conversations.length === 0 ? (
            <div className="chat-empty">Диалогов пока нет. Откройте объявление в каталоге, чтобы написать продавцу.</div>
          ) : conversations.map((conversation) => (
            <button
              type="button"
              key={conversation.id}
              className={selectedConversationId === conversation.id ? 'chat-conversation chat-conversation-active' : 'chat-conversation'}
              onClick={() => setSelectedConversationId(conversation.id)}
            >
              <span className="chat-conversation-title">
                {listingTitles[conversation.listing_id] ?? 'Объявление'}
              </span>
              <span className="chat-conversation-meta">
                {conversation.buyer_id === user.id ? 'Вы покупатель' : 'Вы продавец'}
                {conversation.unread_count > 0 && (
                  <span className="chat-unread">{conversation.unread_count}</span>
                )}
              </span>
            </button>
          ))}
        </aside>

        <section className="chat-window" aria-label="Переписка">
          {!selectedConversation ? (
            <div className="chat-empty chat-window-empty">
              <span aria-hidden="true">✉</span>
              <p>Выберите диалог или начните общение из карточки объявления.</p>
            </div>
          ) : (
            <>
              <header className="chat-window-heading">
                <div>
                  <strong>{listingTitles[selectedConversation.listing_id] ?? 'Объявление'}</strong>
                  <span>
                    {selectedConversation.buyer_id === user.id
                      ? 'Диалог с продавцом'
                      : 'Диалог с покупателем'}
                  </span>
                </div>
              </header>
              <div className="chat-messages" aria-live="polite">
                {visibleMessages.length === 0 ? (
                  <p className="chat-empty chat-messages-empty">Напишите первое сообщение</p>
                ) : visibleMessages.map((message) => (
                  <article
                    className={message.sender_id === user.id ? 'chat-message chat-message-own' : 'chat-message'}
                    key={message.id}
                  >
                    <p>{message.content}</p>
                    <time dateTime={message.created_at}>
                      {new Date(message.created_at).toLocaleString('ru-RU', {
                        day: 'numeric',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </time>
                  </article>
                ))}
                <div ref={bottomRef} />
              </div>
              <form className="chat-compose" onSubmit={sendMessage}>
                <label className="chat-compose-field">
                  <span className="visually-hidden">Новое сообщение</span>
                  <textarea
                    required
                    maxLength={5000}
                    rows={2}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Напишите сообщение..."
                  />
                </label>
                <button type="submit" disabled={isSending || !draft.trim()}>
                  Отправить
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </section>
  )
}
