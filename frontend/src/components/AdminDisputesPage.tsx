import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  dealsApi,
  getPrivateImageUrl,
} from '../api'
import type {
  Dispute,
  DisputeAuditEntry,
  DisputeDecision,
  DisputeStatus,
} from '../api'
import './AdminDisputesPage.css'

const DISPUTE_STATUSES: DisputeStatus[] = [
  'WAITING_SELLER',
  'WAITING_BUYER',
  'UNDER_REVIEW',
  'RESOLVING',
  'RESOLVED',
]

const STATUS_LABELS: Record<DisputeStatus, string> = {
  WAITING_SELLER: 'Ожидается ответ продавца',
  WAITING_BUYER: 'Ожидается ответ покупателя',
  UNDER_REVIEW: 'На рассмотрении',
  RESOLVING: 'Выполняется решение',
  RESOLVED: 'Решение выполнено',
}

const DECISION_LABELS: Record<DisputeDecision, string> = {
  REFUND_BUYER: 'Возврат покупателю',
  PAY_SELLER: 'Выплата продавцу',
  PARTIAL_REFUND: 'Частичный возврат',
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

function PrivateImage({ reference }: { reference: string }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let objectUrl: string | null = null
    getPrivateImageUrl(reference)
      .then((imageUrl) => {
        objectUrl = imageUrl
        if (active) setUrl(imageUrl)
        else URL.revokeObjectURL(imageUrl)
      })
      .catch(() => {
        if (active) setUrl(null)
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [reference])

  return url
    ? <img className="admin-dispute-image" src={url} alt="Фото-доказательство" />
    : <span className="admin-dispute-muted">Изображение недоступно</span>
}

export default function AdminDisputesPage() {
  const [statusFilter, setStatusFilter] = useState<DisputeStatus | ''>('')
  const [disputes, setDisputes] = useState<Dispute[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [audit, setAudit] = useState<DisputeAuditEntry[]>([])
  const [auditForId, setAuditForId] = useState<string | null>(null)
  const [participant, setParticipant] = useState<'buyer' | 'seller'>('buyer')
  const [evidenceNote, setEvidenceNote] = useState('')
  const [decision, setDecision] = useState<DisputeDecision>('PAY_SELLER')
  const [refundAmount, setRefundAmount] = useState('')
  const [resolutionNote, setResolutionNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loadedKey, setLoadedKey] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const requestKey = `${statusFilter}:${revision}`
  const isLoading = loadedKey !== requestKey

  useEffect(() => {
    let active = true
    dealsApi.listAdminDisputes(statusFilter || undefined)
      .then((items) => {
        if (active) {
          setDisputes(items)
          setSelectedId((current) =>
            current && items.some((item) => item.id === current)
              ? current
              : items[0]?.id ?? null,
          )
          setError(null)
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(getErrorMessage(loadError))
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey)
      })
    return () => {
      active = false
    }
  }, [requestKey, statusFilter])

  useEffect(() => {
    let active = true
    if (!selectedId) {
      return () => {
        active = false
      }
    }
    dealsApi.getDisputeAudit(selectedId)
      .then((entries) => {
        if (active) {
          setAudit(entries)
          setAuditForId(selectedId)
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(getErrorMessage(loadError))
      })
    return () => {
      active = false
    }
  }, [revision, selectedId])

  const selectedDispute = disputes.find((item) => item.id === selectedId) ?? null
  const canAct = selectedDispute !== null &&
    !['RESOLVING', 'RESOLVED'].includes(selectedDispute.status)

  async function performAction(action: () => Promise<unknown>): Promise<boolean> {
    setIsBusy(true)
    setError(null)
    try {
      await action()
      setRevision((value) => value + 1)
      return true
    } catch (actionError) {
      setError(getErrorMessage(actionError))
      return false
    } finally {
      setIsBusy(false)
    }
  }

  function requestEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDispute) return
    void performAction(() => dealsApi.requestDisputeEvidence(selectedDispute.id, {
      participant,
      note: evidenceNote.trim(),
    })).then((succeeded) => {
      if (succeeded) setEvidenceNote('')
    })
  }

  function resolveDispute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDispute) return
    const payload: {
      decision: DisputeDecision
      refund_amount?: string
      note: string
    } = {
      decision,
      note: resolutionNote.trim(),
    }
    if (decision === 'PARTIAL_REFUND') payload.refund_amount = refundAmount
    void performAction(() => dealsApi.resolveDispute(selectedDispute.id, payload))
      .then((succeeded) => {
        if (!succeeded) return
        setResolutionNote('')
        setRefundAmount('')
      })
  }

  return (
    <section className="admin-disputes-page" aria-labelledby="admin-disputes-title">
      <header className="admin-disputes-heading">
        <div>
          <p>ПАНЕЛЬ МОДЕРАЦИИ</p>
          <h1 id="admin-disputes-title">Разбор <span>споров</span></h1>
          <p>Запрос доказательств, история и решения по защищенным сделкам.</p>
        </div>
        <div className="admin-disputes-controls">
          <label className="admin-dispute-filter">
            <span>Статус</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as DisputeStatus | '')}
            >
              <option value="">Все споры</option>
              {DISPUTE_STATUSES.map((status) => (
                <option key={status} value={status}>{STATUS_LABELS[status]}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="admin-dispute-secondary"
            onClick={() => setRevision((value) => value + 1)}
          >
            Обновить список
          </button>
        </div>
      </header>

      {error && <div className="admin-disputes-alert" role="alert">{error}</div>}

      <div className="admin-disputes-layout">
        <aside className="admin-disputes-list" aria-label="Список споров">
          {isLoading ? (
            <p className="admin-disputes-empty">Загружаем споры...</p>
          ) : disputes.length === 0 ? (
            <p className="admin-disputes-empty">Споров с таким статусом нет</p>
          ) : disputes.map((item) => (
            <button
              type="button"
              key={item.id}
              className={selectedId === item.id ? 'admin-dispute-card admin-dispute-card-active' : 'admin-dispute-card'}
              onClick={() => setSelectedId(item.id)}
            >
              <strong>{item.reason.replaceAll('_', ' ')}</strong>
              <span>{STATUS_LABELS[item.status]}</span>
              <small>{new Date(item.created_at).toLocaleDateString('ru-RU')}</small>
            </button>
          ))}
        </aside>

        <section className="admin-dispute-detail" aria-label="Детали спора">
          {!selectedDispute ? (
            <p className="admin-disputes-empty">Выберите спор для просмотра.</p>
          ) : (
            <>
              <header className="admin-dispute-detail-heading">
                <div>
                  <p>СДЕЛКА {selectedDispute.deal_id}</p>
                  <h2>{STATUS_LABELS[selectedDispute.status]}</h2>
                </div>
                <span>{selectedDispute.reason.replaceAll('_', ' ')}</span>
              </header>
              <p className="admin-dispute-description">{selectedDispute.description}</p>
              <section className="admin-dispute-evidence">
                <h3>Доказательства</h3>
                {selectedDispute.evidence.length === 0 ? (
                  <p className="admin-dispute-muted">Доказательства пока не добавлены.</p>
                ) : selectedDispute.evidence.map((entry) => (
                  <article key={entry.id}>
                    <strong>{entry.evidence_type} · {entry.submitted_by}</strong>
                    <p>{entry.content || 'Фото-доказательство'}</p>
                    {entry.image_url && <PrivateImage reference={entry.image_url} />}
                    <time dateTime={entry.created_at}>
                      {new Date(entry.created_at).toLocaleString('ru-RU')}
                    </time>
                  </article>
                ))}
              </section>

              {selectedDispute.resolution && (
                <section className="admin-dispute-result">
                  <h3>Решение: {DECISION_LABELS[selectedDispute.resolution]}</h3>
                  {selectedDispute.refund_amount && <p>Возврат: {selectedDispute.refund_amount} ₽</p>}
                  {selectedDispute.resolution_note && <p>{selectedDispute.resolution_note}</p>}
                </section>
              )}

              {canAct && (
                <div className="admin-dispute-actions">
                  <form className="admin-dispute-form" onSubmit={requestEvidence}>
                    <h3>Запросить доказательства</h3>
                    <label className="admin-dispute-field">
                      <span>Участник</span>
                      <select
                        value={participant}
                        onChange={(event) => setParticipant(event.target.value as 'buyer' | 'seller')}
                      >
                        <option value="buyer">Покупатель</option>
                        <option value="seller">Продавец</option>
                      </select>
                    </label>
                    <label className="admin-dispute-field">
                      <span>Что нужно предоставить</span>
                      <textarea
                        required
                        minLength={1}
                        maxLength={2000}
                        value={evidenceNote}
                        onChange={(event) => setEvidenceNote(event.target.value)}
                      />
                    </label>
                    <button className="admin-dispute-secondary" disabled={isBusy}>Отправить запрос</button>
                  </form>

                  <form className="admin-dispute-form" onSubmit={resolveDispute}>
                    <h3>Решить спор</h3>
                    <label className="admin-dispute-field">
                      <span>Решение</span>
                      <select
                        value={decision}
                        onChange={(event) => setDecision(event.target.value as DisputeDecision)}
                      >
                        {Object.entries(DECISION_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </label>
                    {decision === 'PARTIAL_REFUND' && (
                      <label className="admin-dispute-field">
                        <span>Сумма возврата, ₽</span>
                        <input
                          required
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={refundAmount}
                          onChange={(event) => setRefundAmount(event.target.value)}
                        />
                      </label>
                    )}
                    <label className="admin-dispute-field">
                      <span>Обоснование</span>
                      <textarea
                        required
                        minLength={1}
                        maxLength={300}
                        value={resolutionNote}
                        onChange={(event) => setResolutionNote(event.target.value)}
                      />
                    </label>
                    <button className="admin-dispute-primary" disabled={isBusy}>Запустить решение</button>
                  </form>
                </div>
              )}

              <section className="admin-dispute-audit">
                <h3>История действий</h3>
                {auditForId !== selectedId || audit.length === 0 ? (
                  <p className="admin-dispute-muted">История пуста.</p>
                ) : (
                  <ol>
                    {audit.map((entry) => (
                      <li key={entry.id}>
                        <strong>{entry.action}</strong>
                        <time dateTime={entry.created_at}>
                          {new Date(entry.created_at).toLocaleString('ru-RU')}
                        </time>
                        <span>{JSON.stringify(entry.details)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </>
          )}
        </section>
      </div>
    </section>
  )
}
