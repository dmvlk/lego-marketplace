import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  catalogApi,
  dealsApi,
  deliveryApi,
  getPrivateImageUrl,
  paymentsApi,
  reviewsApi,
} from '../api'
import type {
  Deal,
  Dispute,
  DisputeDecision,
  DisputeReason,
  EvidenceType,
  Offer,
  Shipment,
  ShipmentStatus,
  TransactionType,
  UserProfile,
} from '../api'
import './DealsPage.css'

type DealsTab = 'purchases' | 'sales' | 'offers'

const DEAL_STATUS_LABELS: Record<Deal['status'], string> = {
  PENDING_CONFIRMATION: 'Ожидает подтверждения',
  AWAITING_PAYMENT: 'Ожидает оплаты',
  PAID: 'Оплачена',
  SHIPPED: 'В пути',
  INSPECTION: 'На осмотре',
  DISPUTED: 'Открыт спор',
  COMPLETED: 'Завершена',
  CANCELLED: 'Отменена',
}

const SHIPMENT_STATUS_LABELS: Record<ShipmentStatus, string> = {
  CREATED: 'Создано',
  IN_TRANSIT: 'В пути',
  OUT_FOR_DELIVERY: 'Курьер доставляет',
  EXCEPTION: 'Проблема с доставкой',
  RETURNED: 'Возвращено',
  DELIVERED: 'Доставлено',
}

const OFFER_STATUS_LABELS: Record<Offer['status'], string> = {
  OPEN: 'Ожидает ответа',
  COUNTERED: 'Получено встречное предложение',
  ACCEPTED: 'Принято',
  REJECTED: 'Отклонено',
}

const DISPUTE_STATUS_LABELS: Record<Dispute['status'], string> = {
  WAITING_SELLER: 'Ожидается ответ продавца',
  WAITING_BUYER: 'Ожидается ответ покупателя',
  UNDER_REVIEW: 'На рассмотрении',
  RESOLVING: 'Выполняется решение',
  RESOLVED: 'Решение выполнено',
}

const DISPUTE_REASON_LABELS: Record<DisputeReason, string> = {
  NOT_AS_DESCRIBED: 'Товар не соответствует описанию',
  DAMAGED: 'Товар поврежден',
  MISSING_PARTS: 'Не хватает деталей',
  WRONG_ITEM: 'Получен другой товар',
  NOT_DELIVERED: 'Товар не доставлен',
  OTHER: 'Другая причина',
}

const DISPUTE_DECISION_LABELS: Record<DisputeDecision, string> = {
  REFUND_BUYER: 'Возврат покупателю',
  PAY_SELLER: 'Выплата продавцу',
  PARTIAL_REFUND: 'Частичный возврат',
}

const TRACKING_TRANSITIONS: Partial<Record<ShipmentStatus, ShipmentStatus[]>> = {
  CREATED: ['IN_TRANSIT', 'EXCEPTION'],
  IN_TRANSIT: ['OUT_FOR_DELIVERY', 'EXCEPTION', 'RETURNED'],
  OUT_FOR_DELIVERY: ['IN_TRANSIT', 'EXCEPTION', 'RETURNED'],
  EXCEPTION: ['IN_TRANSIT', 'OUT_FOR_DELIVERY', 'RETURNED'],
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

function formatPrice(price: string | number): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 2,
  }).format(Number(price))
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

function EvidenceImage({ reference }: { reference: string }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    let objectUrl: string | null = null
    getPrivateImageUrl(reference)
      .then((url) => {
        objectUrl = url
        if (active) {
          setImageUrl(url)
        } else {
          URL.revokeObjectURL(url)
        }
      })
      .catch(() => {
        if (active) {
          setError(true)
        }
      })
    return () => {
      active = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [reference])

  if (error) {
    return <span className="deal-muted">Не удалось загрузить изображение</span>
  }
  if (!imageUrl) {
    return <span className="deal-muted">Загружаем изображение...</span>
  }
  return <img className="dispute-evidence-image" src={imageUrl} alt="Фото-доказательство" />
}

interface DealsPageProps {
  user: UserProfile
  initialDealId: string | null
  initialTab: DealsTab
}

export default function DealsPage({ user, initialDealId, initialTab }: DealsPageProps) {
  const [tab, setTab] = useState<DealsTab>(initialTab)
  const [purchases, setPurchases] = useState<Deal[]>([])
  const [sales, setSales] = useState<Deal[]>([])
  const [offers, setOffers] = useState<Offer[]>([])
  const [listingTitles, setListingTitles] = useState<Record<string, string>>({})
  const [selectedDealId, setSelectedDealId] = useState<string | null>(initialDealId)
  const [dealData, setDealData] = useState<Deal | null>(null)
  const [shipmentData, setShipmentData] = useState<{
    dealId: string
    shipment: Shipment | null
  } | null>(null)
  const [disputeData, setDisputeData] = useState<{
    dealId: string
    dispute: Dispute | null
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadedListKey, setLoadedListKey] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [refreshRevision, setRefreshRevision] = useState(0)
  const [detailRevision, setDetailRevision] = useState(0)
  const [counterAmounts, setCounterAmounts] = useState<Record<string, string>>({})
  const [carrier, setCarrier] = useState('')
  const [trackingNumber, setTrackingNumber] = useState('')
  const [trackingStatus, setTrackingStatus] = useState<ShipmentStatus | ''>('')
  const [trackingNote, setTrackingNote] = useState('')
  const [showDisputeForm, setShowDisputeForm] = useState(false)
  const [disputeReason, setDisputeReason] = useState<DisputeReason>('NOT_AS_DESCRIBED')
  const [disputeDescription, setDisputeDescription] = useState('')
  const [evidenceType, setEvidenceType] = useState<EvidenceType>('TEXT')
  const [evidenceText, setEvidenceText] = useState('')
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null)
  const [reviewRating, setReviewRating] = useState('5')
  const [reviewComment, setReviewComment] = useState('')
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const listRequestKey = `${user.id}:${refreshRevision}`
  const isLoading = loadedListKey !== listRequestKey
  const selectedDeal = dealData?.id === selectedDealId ? dealData : null
  const shipment = shipmentData?.dealId === selectedDealId
    ? shipmentData.shipment
    : null
  const dispute = disputeData?.dealId === selectedDealId
    ? disputeData.dispute
    : null

  useEffect(() => {
    let active = true
    Promise.all([
      dealsApi.getPurchases(),
      dealsApi.getSales(),
      dealsApi.listOffers(),
    ])
      .then(async ([purchaseList, salesList, offerList]) => {
        if (!active) return
        setPurchases(purchaseList)
        setSales(salesList)
        setOffers(offerList)
        const listingIds = [...new Set(offerList.map((offer) => offer.listing_id))]
        const titles = await Promise.all(
          listingIds.map(async (listingId) => {
            try {
              const listing = await catalogApi.getListing(listingId)
              return [listingId, listing.title] as const
            } catch (loadError) {
              if (isNotFound(loadError)) {
                return [listingId, 'Объявление больше недоступно'] as const
              }
              throw loadError
            }
          }),
        )
        if (active) {
          setListingTitles(Object.fromEntries(titles))
          setError(null)
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(getErrorMessage(loadError))
      })
      .finally(() => {
        if (active) setLoadedListKey(listRequestKey)
      })
    return () => {
      active = false
    }
  }, [listRequestKey, user.id])

  useEffect(() => {
    let active = true
    if (!selectedDealId) {
      return () => {
        active = false
      }
    }

    Promise.all([
      dealsApi.getDeal(selectedDealId),
      deliveryApi.getShipmentByDeal(selectedDealId).catch((loadError: unknown) => {
        if (isNotFound(loadError)) return null
        throw loadError
      }),
      dealsApi.getDealDispute(selectedDealId),
    ])
      .then(([deal, loadedShipment, loadedDispute]) => {
        if (active) {
          setDealData(deal)
          setShipmentData({ dealId: selectedDealId, shipment: loadedShipment })
          setDisputeData({ dealId: selectedDealId, dispute: loadedDispute })
          setError(null)
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(getErrorMessage(loadError))
      })
    return () => {
      active = false
    }
  }, [detailRevision, selectedDealId])

  async function performAction(
    action: () => Promise<unknown>,
    message?: string,
  ): Promise<boolean> {
    setIsBusy(true)
    setError(null)
    setSuccessMessage(null)
    try {
      await action()
      if (message) setSuccessMessage(message)
      setDetailRevision((revision) => revision + 1)
      setRefreshRevision((revision) => revision + 1)
      return true
    } catch (actionError) {
      setError(getErrorMessage(actionError))
      return false
    } finally {
      setIsBusy(false)
    }
  }

  async function acceptOffer(offer: Offer, transactionType: TransactionType) {
    setIsBusy(true)
    setError(null)
    try {
      const deal = await dealsApi.acceptOffer(offer.id, transactionType)
      setSelectedDealId(deal.id)
      setTab(deal.buyer_id === user.id ? 'purchases' : 'sales')
      setDetailRevision((revision) => revision + 1)
      setRefreshRevision((revision) => revision + 1)
      setSuccessMessage('Предложение принято, сделка создана')
    } catch (actionError) {
      setError(getErrorMessage(actionError))
    } finally {
      setIsBusy(false)
    }
  }

  function submitShipment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDeal) return
    void performAction(
      () => deliveryApi.createShipment(selectedDeal.id, carrier),
      'Отправление создано',
    ).then((succeeded) => {
      if (succeeded) setCarrier('')
    })
  }

  function submitTracking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!shipment) return
    const payload: {
      tracking_number?: string
      status?: ShipmentStatus
      note?: string
    } = {}
    if (trackingNumber.trim()) payload.tracking_number = trackingNumber.trim()
    if (trackingStatus) payload.status = trackingStatus
    if (trackingNote.trim()) payload.note = trackingNote.trim()
    void performAction(
      () => deliveryApi.updateTracking(shipment.id, payload),
      'Данные отслеживания обновлены',
    ).then((succeeded) => {
      if (!succeeded) return
      setTrackingNumber('')
      setTrackingStatus('')
      setTrackingNote('')
    })
  }

  function submitDispute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDeal) return
    void performAction(
      () => dealsApi.openDispute(selectedDeal.id, {
        reason: disputeReason,
        description: disputeDescription.trim(),
      }),
      'Спор открыт',
    ).then((succeeded) => {
      if (!succeeded) return
      setShowDisputeForm(false)
      setDisputeDescription('')
    })
  }

  function submitEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!dispute) return
    if (evidenceFile) {
      void performAction(
        () => dealsApi.uploadDisputeImage(dispute.id, evidenceFile, evidenceText.trim()),
        'Фото добавлено к спору',
      ).then((succeeded) => {
        if (!succeeded) return
        setEvidenceFile(null)
        setEvidenceText('')
      })
      return
    }
    void performAction(
      () => dealsApi.addDisputeEvidence(dispute.id, {
        evidence_type: evidenceType,
        content: evidenceText.trim(),
      }),
      'Доказательство добавлено',
    ).then((succeeded) => {
      if (succeeded) setEvidenceText('')
    })
  }

  function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDeal) return
    void performAction(
      () => reviewsApi.createReview(selectedDeal.id, {
        rating: Number(reviewRating),
        comment: reviewComment.trim() || null,
      }),
      'Отзыв опубликован',
    ).then((succeeded) => {
      if (succeeded) setReviewComment('')
    })
  }

  const currentDeals = tab === 'purchases' ? purchases : sales
  const isBuyer = selectedDeal?.buyer_id === user.id
  const canEditEvidence = dispute !== null &&
    !['RESOLVING', 'RESOLVED'].includes(dispute.status)
  const allowedTrackingStatuses = shipment
    ? TRACKING_TRANSITIONS[shipment.status] ?? []
    : []
  const trackingNeedsNumber = trackingStatus !== '' && [
    'IN_TRANSIT',
    'OUT_FOR_DELIVERY',
    'EXCEPTION',
    'RETURNED',
  ].includes(trackingStatus)
  const hasTrackingNumber = Boolean(trackingNumber.trim() || shipment?.tracking_number)

  return (
    <section className="deals-page" aria-labelledby="deals-title">
      <header className="deals-page-heading">
        <div>
          <p className="deals-eyebrow">ВАШИ ДОГОВОРЕННОСТИ</p>
          <h1 id="deals-title">Сделки <span>и предложения</span></h1>
          <p>Покупки, продажи, доставка и защищенные сделки в одном месте.</p>
        </div>
      </header>

      {error && (
        <div className="deals-alert" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => {
            setError(null)
            setRefreshRevision((revision) => revision + 1)
            setDetailRevision((revision) => revision + 1)
          }}>Повторить</button>
        </div>
      )}
      {successMessage && <p className="deals-success" role="status">{successMessage}</p>}

      <div className="deals-layout">
        <section className="deals-list-panel" aria-label="Список сделок">
          <nav className="deals-tabs" aria-label="Тип операций">
            {([
              ['purchases', 'Покупки'],
              ['sales', 'Продажи'],
              ['offers', 'Предложения'],
            ] as const).map(([key, label]) => (
              <button
                type="button"
                key={key}
                className={tab === key ? 'deals-tab deals-tab-active' : 'deals-tab'}
                aria-current={tab === key ? 'page' : undefined}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </nav>

          {isLoading ? (
            <div className="deals-empty" role="status">Загружаем...</div>
          ) : tab === 'offers' ? (
            <div className="deals-items">
              {offers.length === 0 ? (
                <div className="deals-empty">Предложений пока нет</div>
              ) : offers.map((offer) => (
                <article className="offer-card" key={offer.id}>
                  <div className="deal-card-heading">
                    <strong>{listingTitles[offer.listing_id] ?? 'Объявление'}</strong>
                    <span className={`deal-status deal-status-${offer.status.toLowerCase()}`}>
                      {OFFER_STATUS_LABELS[offer.status]}
                    </span>
                  </div>
                  <p>{formatPrice(offer.amount)}</p>
                  <small>
                    {offer.sender_id === user.id
                      ? 'Ваше предложение'
                      : 'Предложение для вас'}
                  </small>
                  {offer.recipient_id === user.id && offer.status === 'OPEN' && (
                    <div className="offer-actions">
                      <label className="deal-field">
                        <span>Встречная цена, ₽</span>
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={counterAmounts[offer.id] ?? ''}
                          onChange={(event) => setCounterAmounts((values) => ({
                            ...values,
                            [offer.id]: event.target.value,
                          }))}
                        />
                      </label>
                      <button
                        type="button"
                        className="deal-secondary-button"
                        disabled={isBusy || !counterAmounts[offer.id]}
                        onClick={() => void performAction(
                          () => dealsApi.counterOffer(offer.id, counterAmounts[offer.id]),
                          'Встречное предложение отправлено',
                        ).then((succeeded) => {
                          if (succeeded) {
                            setCounterAmounts((values) => ({
                              ...values,
                              [offer.id]: '',
                            }))
                          }
                        })}
                      >
                        Предложить цену
                      </button>
                      <button
                        type="button"
                        className="deal-secondary-button"
                        disabled={isBusy}
                        onClick={() => void performAction(
                          () => dealsApi.rejectOffer(offer.id),
                          'Предложение отклонено',
                        )}
                      >
                        Отклонить
                      </button>
                      <button
                        type="button"
                        className="deal-primary-button"
                        disabled={isBusy}
                        onClick={() => void acceptOffer(offer, 'ONLINE_PROTECTED')}
                      >
                        Принять с защитой
                      </button>
                      <button
                        type="button"
                        className="deal-secondary-button"
                        disabled={isBusy}
                        onClick={() => void acceptOffer(offer, 'OFFLINE')}
                      >
                        Принять для встречи
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="deals-items">
              {currentDeals.length === 0 ? (
                <div className="deals-empty">
                  {tab === 'purchases' ? 'Покупок пока нет' : 'Продаж пока нет'}
                </div>
              ) : currentDeals.map((deal) => (
                <button
                  type="button"
                  key={deal.id}
                  className={selectedDealId === deal.id ? 'deal-card deal-card-active' : 'deal-card'}
                  onClick={() => setSelectedDealId(deal.id)}
                >
                  <span className="deal-card-heading">
                    <strong>{deal.snapshot.title}</strong>
                    <span className={`deal-status deal-status-${deal.status.toLowerCase()}`}>
                      {DEAL_STATUS_LABELS[deal.status]}
                    </span>
                  </span>
                  <span className="deal-card-price">{formatPrice(deal.agreed_price)}</span>
                  <span className="deal-card-caption">
                    {deal.transaction_type === 'ONLINE_PROTECTED'
                      ? 'Защищенная онлайн-сделка'
                      : 'Офлайн-встреча'}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="deal-detail-panel" aria-label="Детали сделки">
          {!selectedDeal ? (
                <div className="deals-empty deals-detail-empty">
              <span aria-hidden="true">↖</span>
                  <p>
                    {selectedDealId
                      ? 'Загружаем данные сделки...'
                      : 'Выберите сделку, чтобы увидеть детали и доступные действия.'}
                  </p>
            </div>
          ) : (
            <article className="deal-detail">
              <header className="deal-detail-heading">
                <div>
                  <p className="deals-eyebrow">СДЕЛКА</p>
                  <h2>{selectedDeal.snapshot.title}</h2>
                </div>
                <span className={`deal-status deal-status-${selectedDeal.status.toLowerCase()}`}>
                  {DEAL_STATUS_LABELS[selectedDeal.status]}
                </span>
              </header>
              <dl className="deal-facts">
                <div><dt>Сумма</dt><dd>{formatPrice(selectedDeal.agreed_price)}</dd></div>
                <div><dt>Способ</dt><dd>{selectedDeal.transaction_type === 'ONLINE_PROTECTED' ? 'Онлайн с защитой' : 'Офлайн'}</dd></div>
                <div><dt>Покупатель</dt><dd>{isBuyer ? 'Вы' : selectedDeal.buyer_id}</dd></div>
                <div><dt>Продавец</dt><dd>{isBuyer ? selectedDeal.seller_id : 'Вы'}</dd></div>
              </dl>

              {selectedDeal.status === 'AWAITING_PAYMENT' && isBuyer && (
                <div className="deal-action-block">
                  <p>Демо-оплата авторизует платеж, но реальные деньги не списываются.</p>
                  <button
                    type="button"
                    className="deal-primary-button"
                    disabled={isBusy}
                    onClick={() => void performAction(
                      () => paymentsApi.startDealPayment(selectedDeal.id, crypto.randomUUID()),
                      'Оплата авторизована в демо-режиме',
                    )}
                  >
                    Оплатить в демо-режиме
                  </button>
                </div>
              )}

              {selectedDeal.status === 'PENDING_CONFIRMATION' && selectedDeal.transaction_type === 'OFFLINE' && (
                <div className="deal-action-block">
                  <p>
                    Подтверждения: покупатель - {selectedDeal.buyer_confirmed ? 'готово' : 'ожидается'},
                    {' '}продавец - {selectedDeal.seller_confirmed ? 'готово' : 'ожидается'}
                  </p>
                  {(isBuyer ? !selectedDeal.buyer_confirmed : !selectedDeal.seller_confirmed) && (
                    <button
                      type="button"
                      className="deal-primary-button"
                      disabled={isBusy}
                      onClick={() => void performAction(
                        () => dealsApi.confirmOffline(selectedDeal.id),
                        'Подтверждение сделки сохранено',
                      )}
                    >
                      Подтвердить сделку
                    </button>
                  )}
                </div>
              )}

              {selectedDeal.status === 'PAID' && !isBuyer && selectedDeal.transaction_type === 'ONLINE_PROTECTED' && !shipment && (
                <form className="deal-form-block" onSubmit={submitShipment}>
                  <h3>Оформить отправление</h3>
                  <label className="deal-field">
                    <span>Служба доставки</span>
                    <input
                      required
                      minLength={2}
                      maxLength={100}
                      value={carrier}
                      onChange={(event) => setCarrier(event.target.value)}
                      placeholder="Например, Почта России"
                    />
                  </label>
                  <button className="deal-primary-button" disabled={isBusy}>Создать отправление</button>
                </form>
              )}

              {shipment && (
                <section className="shipment-panel" aria-labelledby="shipment-title">
                  <h3 id="shipment-title">Доставка</h3>
                  <p><strong>{shipment.carrier}</strong> · {SHIPMENT_STATUS_LABELS[shipment.status]}</p>
                  <p>Трек-номер: {shipment.tracking_number || 'пока не указан'}</p>
                  {shipment.tracking_events.length > 0 && (
                    <ol className="tracking-events">
                      {shipment.tracking_events.map((event) => (
                        <li key={event.id}>
                          <strong>{SHIPMENT_STATUS_LABELS[event.status]}</strong>
                          <time dateTime={event.created_at}>
                            {new Date(event.created_at).toLocaleString('ru-RU')}
                          </time>
                          {event.note && <span>{event.note}</span>}
                          {event.tracking_number && <span>Трек-номер: {event.tracking_number}</span>}
                        </li>
                      ))}
                    </ol>
                  )}
                  {!isBuyer && !['DELIVERED', 'RETURNED'].includes(shipment.status) && (
                    <form className="deal-form-block tracking-form" onSubmit={submitTracking}>
                      <h4>Обновить отслеживание</h4>
                      <label className="deal-field">
                        <span>Новый трек-номер</span>
                        <input
                          minLength={3}
                          maxLength={120}
                          value={trackingNumber}
                          onChange={(event) => setTrackingNumber(event.target.value)}
                        />
                      </label>
                      <label className="deal-field">
                        <span>Статус отправления</span>
                        <select
                          value={trackingStatus}
                          onChange={(event) => setTrackingStatus(event.target.value as ShipmentStatus | '')}
                        >
                          <option value="">Не менять статус</option>
                          {allowedTrackingStatuses.map((status) => (
                            <option key={status} value={status}>{SHIPMENT_STATUS_LABELS[status]}</option>
                          ))}
                        </select>
                      </label>
                      <label className="deal-field">
                        <span>Примечание</span>
                        <input
                          maxLength={300}
                          value={trackingNote}
                          onChange={(event) => setTrackingNote(event.target.value)}
                        />
                      </label>
                      <button
                        className="deal-secondary-button"
                        disabled={
                          isBusy ||
                          (!trackingNumber.trim() && !trackingStatus && !trackingNote.trim()) ||
                          (trackingNeedsNumber && !hasTrackingNumber)
                        }
                      >
                        Сохранить отслеживание
                      </button>
                    </form>
                  )}
                  {isBuyer && ['IN_TRANSIT', 'OUT_FOR_DELIVERY', 'EXCEPTION'].includes(shipment.status) && shipment.tracking_number && (
                    <button
                      type="button"
                      className="deal-primary-button"
                      disabled={isBusy}
                      onClick={() => void performAction(
                        () => deliveryApi.confirmDelivered(shipment.id),
                        'Доставка подтверждена, начался период осмотра',
                      )}
                    >
                      Подтвердить получение
                    </button>
                  )}
                </section>
              )}

              {selectedDeal.status === 'INSPECTION' && isBuyer && (
                <div className="deal-action-block">
                  {selectedDeal.inspection_deadline_at && (
                    <p>
                      Осмотр до {new Date(selectedDeal.inspection_deadline_at).toLocaleString('ru-RU')}
                    </p>
                  )}
                  <button
                    type="button"
                    className="deal-primary-button"
                    disabled={isBusy}
                    onClick={() => void performAction(
                      () => dealsApi.confirmInspection(selectedDeal.id),
                      'Получение подтверждено',
                    )}
                  >
                    Подтвердить товар
                  </button>
                  <button
                    type="button"
                    className="deal-secondary-button"
                    disabled={isBusy}
                    onClick={() => setShowDisputeForm((shown) => !shown)}
                  >Открыть спор</button>
                </div>
              )}

              {['PAID', 'SHIPPED'].includes(selectedDeal.status) &&
                isBuyer &&
                selectedDeal.transaction_type === 'ONLINE_PROTECTED' && (
                <div className="deal-action-block">
                  <p>Если заказ не доставлен или возникла проблема, сообщите о ней через спор.</p>
                  <button
                    type="button"
                    className="deal-secondary-button"
                    disabled={isBusy}
                    onClick={() => setShowDisputeForm((shown) => !shown)}
                  >
                    Открыть спор
                  </button>
                </div>
              )}

              {showDisputeForm &&
                ['PAID', 'SHIPPED', 'INSPECTION'].includes(selectedDeal.status) &&
                isBuyer && (
                <form className="deal-form-block" onSubmit={submitDispute}>
                  <h3>Открыть спор</h3>
                  <label className="deal-field">
                    <span>Причина</span>
                    <select
                      value={disputeReason}
                      onChange={(event) => setDisputeReason(event.target.value as DisputeReason)}
                    >
                      {Object.entries(DISPUTE_REASON_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="deal-field">
                    <span>Подробности</span>
                    <textarea
                      required
                      minLength={10}
                      maxLength={5000}
                      value={disputeDescription}
                      onChange={(event) => setDisputeDescription(event.target.value)}
                    />
                  </label>
                  <button className="deal-primary-button" disabled={isBusy}>Отправить спор</button>
                </form>
              )}

              {selectedDeal.status === 'DISPUTED' && (
                <section className="dispute-panel" aria-labelledby="dispute-title">
                  <h3 id="dispute-title">Спор</h3>
                  {!dispute ? (
                    <p className="deal-muted">Загружаем информацию о споре...</p>
                  ) : (
                    <>
                      <p><strong>{DISPUTE_REASON_LABELS[dispute.reason]}</strong></p>
                      <p>{dispute.description}</p>
                      <p className="deal-muted">{DISPUTE_STATUS_LABELS[dispute.status]}</p>
                      {dispute.response_due_at && (
                        <p>Ответ требуется до {new Date(dispute.response_due_at).toLocaleString('ru-RU')}</p>
                      )}
                      {dispute.resolution && (
                        <p>
                          Решение: {DISPUTE_DECISION_LABELS[dispute.resolution]}
                          {dispute.refund_amount && ` - ${formatPrice(dispute.refund_amount)}`}
                        </p>
                      )}
                      {dispute.resolution_note && <p>{dispute.resolution_note}</p>}
                      <ul className="evidence-list">
                        {dispute.evidence.map((item) => (
                          <li key={item.id}>
                            <span className="evidence-type">{item.evidence_type}</span>
                            <p>{item.content || 'Фото-доказательство'}</p>
                            {item.image_url && <EvidenceImage reference={item.image_url} />}
                            <time dateTime={item.created_at}>
                              {new Date(item.created_at).toLocaleString('ru-RU')}
                            </time>
                          </li>
                        ))}
                      </ul>
                      {canEditEvidence && (
                        <form className="deal-form-block" onSubmit={submitEvidence}>
                          <h4>Добавить доказательство</h4>
                          <label className="deal-field">
                            <span>Тип текста</span>
                            <select
                              value={evidenceType}
                              onChange={(event) => setEvidenceType(event.target.value as EvidenceType)}
                            >
                              <option value="TEXT">Пояснение</option>
                              <option value="MESSAGE">Переписка</option>
                              <option value="TRACKING">Информация об отслеживании</option>
                            </select>
                          </label>
                          <label className="deal-field">
                            <span>{evidenceFile ? 'Подпись к фото' : 'Текст доказательства'}</span>
                            <textarea
                              required={!evidenceFile}
                              maxLength={5000}
                              value={evidenceText}
                              onChange={(event) => setEvidenceText(event.target.value)}
                            />
                          </label>
                          <label className="deal-field">
                            <span>Фото (необязательно)</span>
                            <input
                              type="file"
                              accept="image/jpeg,image/png,image/webp"
                              onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)}
                            />
                          </label>
                          <button
                            className="deal-secondary-button"
                            disabled={isBusy || (!evidenceText.trim() && !evidenceFile)}
                          >
                            Добавить доказательство
                          </button>
                        </form>
                      )}
                    </>
                  )}
                </section>
              )}

              {selectedDeal.status === 'COMPLETED' && isBuyer && (
                <form className="deal-form-block" onSubmit={submitReview}>
                  <h3>Оставить отзыв продавцу</h3>
                  <label className="deal-field">
                    <span>Оценка</span>
                    <select
                      value={reviewRating}
                      onChange={(event) => setReviewRating(event.target.value)}
                    >
                      {[5, 4, 3, 2, 1].map((rating) => (
                        <option key={rating} value={rating}>{rating} из 5</option>
                      ))}
                    </select>
                  </label>
                  <label className="deal-field">
                    <span>Комментарий</span>
                    <textarea
                      maxLength={2000}
                      value={reviewComment}
                      onChange={(event) => setReviewComment(event.target.value)}
                    />
                  </label>
                  <button className="deal-secondary-button" disabled={isBusy}>Опубликовать отзыв</button>
                </form>
              )}

              {['PENDING_CONFIRMATION', 'AWAITING_PAYMENT'].includes(selectedDeal.status) && (
                <button
                  type="button"
                  className="deal-cancel-button"
                  disabled={isBusy}
                  onClick={() => void performAction(
                    () => dealsApi.cancelDeal(selectedDeal.id),
                    'Сделка отменена',
                  )}
                >
                  Отменить сделку
                </button>
              )}
            </article>
          )}
        </section>
      </div>
    </section>
  )
}
