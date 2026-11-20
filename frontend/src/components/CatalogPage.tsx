import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  chatApi,
  catalogApi,
  dealsApi,
  getImageUrl,
  reviewsApi,
} from '../api'
import type {
  CatalogCategory,
  CatalogTheme,
  Listing,
  ListingFilters,
  ListingPage as ListingPageData,
  SellerReviews,
  TransactionType,
  UserProfile,
} from '../api'
import './CatalogPage.css'

interface CatalogPageProps {
  user: UserProfile | null
  onRequestAuth: () => void
  onDealCreated: (dealId: string) => void
  onOpenConversation: (conversationId: string) => void
  onOpenOffers: () => void
}

interface FavoritesPageProps {
  user: UserProfile | null
  onRequestAuth: () => void
  onViewCatalog: () => void
}

const PAGE_SIZE = 12
const INITIAL_FILTERS: ListingFilters = {
  q: '',
  category_id: '',
  theme_id: '',
  condition: '',
  min_price: '',
  max_price: '',
  sort: 'newest',
}

const CONDITION_LABELS: Record<string, string> = {
  NEW: 'Новый',
  USED: 'Б/у',
  RESTORATION: 'На восстановление',
}

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Не удалось связаться с сервером. Проверьте подключение и адрес API.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Не удалось загрузить каталог. Попробуйте ещё раз.'
}

function formatPrice(price: string): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 2,
  }).format(Number(price))
}

function formatListingCount(count: number): string {
  const lastTwoDigits = count % 100
  const lastDigit = count % 10
  const word =
    lastTwoDigits >= 11 && lastTwoDigits <= 14
      ? 'объявлений'
      : lastDigit === 1
        ? 'объявление'
        : lastDigit >= 2 && lastDigit <= 4
          ? 'объявления'
          : 'объявлений'
  return `${count} ${word}`
}

function ListingPhoto({
  listing,
  large = false,
}: {
  listing: Listing
  large?: boolean
}) {
  const [imageFailed, setImageFailed] = useState(false)
  const imageReference = listing.image_references[0]

  if (!imageReference || imageFailed) {
    return (
      <div
        className={large ? 'listing-photo listing-photo-large photo-placeholder' : 'listing-photo photo-placeholder'}
        role="img"
        aria-label={`Нет фото: ${listing.title}`}
      >
        <div className="placeholder-bricks" aria-hidden="true">
          <span className="placeholder-brick placeholder-brick-red" />
          <span className="placeholder-brick placeholder-brick-yellow" />
          <span className="placeholder-brick placeholder-brick-blue" />
        </div>
        <span className="placeholder-category">БРИКМАРКЕТ</span>
      </div>
    )
  }

  return (
    <div className={large ? 'listing-photo listing-photo-large' : 'listing-photo'}>
      <img
        src={getImageUrl(imageReference)}
        alt={listing.title}
        loading={large ? 'eager' : 'lazy'}
        onError={() => setImageFailed(true)}
      />
    </div>
  )
}

function ListingCard({
  listing,
  categoryName,
  themeName,
  isFavorite,
  isFavoritePending,
  favoriteStateLoading,
  onToggleFavorite,
  onOpen,
}: {
  listing: Listing
  categoryName: string
  themeName: string | null
  isFavorite: boolean
  isFavoritePending: boolean
  favoriteStateLoading: boolean
  onToggleFavorite: () => void
  onOpen: () => void
}) {
  return (
    <article className="listing-card">
      <button
        className="listing-card-button"
        type="button"
        onClick={onOpen}
        aria-label={`Подробнее: ${listing.title}`}
      >
        <ListingPhoto listing={listing} />
        <span className="listing-card-content">
          <span className="listing-card-meta">
            <span className="condition-tag">{CONDITION_LABELS[listing.condition] ?? listing.condition}</span>
            <span>{categoryName}</span>
          </span>
          <span className="listing-card-title">{listing.title}</span>
          <span className="listing-card-footer">
            <strong>{formatPrice(listing.price)}</strong>
            <span aria-hidden="true">↗</span>
          </span>
          {themeName && <span className="listing-card-theme">{themeName}</span>}
        </span>
      </button>
      <button
        className={isFavorite ? 'listing-favorite-button is-favorite' : 'listing-favorite-button'}
        type="button"
        aria-label={isFavorite ? 'Убрать из избранного' : 'Добавить в избранное'}
        aria-pressed={isFavorite}
        aria-busy={isFavoritePending || favoriteStateLoading}
        disabled={isFavoritePending || favoriteStateLoading}
        onClick={onToggleFavorite}
      >
        {isFavoritePending || favoriteStateLoading ? '…' : isFavorite ? '♥' : '♡'}
      </button>
    </article>
  )
}

function ListingDialog({
  listing,
  categoryName,
  themeName,
  user,
  onRequestAuth,
  onDealCreated,
  onOpenConversation,
  onOpenOffers,
  onClose,
}: {
  listing: Listing
  categoryName: string
  themeName: string | null
  user?: UserProfile | null
  onRequestAuth?: () => void
  onDealCreated?: (dealId: string) => void
  onOpenConversation?: (conversationId: string) => void
  onOpenOffers?: () => void
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [sellerReviews, setSellerReviews] = useState<SellerReviews | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [offerAmount, setOfferAmount] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [isActionPending, setIsActionPending] = useState(false)

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => {
      if (dialog?.open) {
        dialog.close()
      }
    }
  }, [])

  useEffect(() => {
    let active = true
    reviewsApi.getSellerReviews(listing.seller_id)
      .then((result) => {
        if (active) {
          setSellerReviews(result)
          setReviewError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setReviewError(getErrorMessage(error))
        }
      })
    return () => {
      active = false
    }
  }, [listing.seller_id])

  function requireUser(): boolean {
    if (user) return true
    onRequestAuth?.()
    return false
  }

  async function createDeal(transactionType: TransactionType) {
    if (!requireUser()) return
    setIsActionPending(true)
    setActionError(null)
    try {
      const deal = await dealsApi.createDeal({
        listing_id: listing.id,
        transaction_type: transactionType,
      })
      onDealCreated?.(deal.id)
      setActionMessage('Сделка создана')
    } catch (error) {
      setActionError(getErrorMessage(error))
    } finally {
      setIsActionPending(false)
    }
  }

  async function createOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!requireUser()) return
    setIsActionPending(true)
    setActionError(null)
    try {
      await dealsApi.createOffer({ listing_id: listing.id, amount: offerAmount })
      setActionMessage('Предложение отправлено продавцу')
      setOfferAmount('')
      onOpenOffers?.()
    } catch (error) {
      setActionError(getErrorMessage(error))
    } finally {
      setIsActionPending(false)
    }
  }

  async function startConversation() {
    if (!requireUser()) return
    setIsActionPending(true)
    setActionError(null)
    try {
      const conversation = await chatApi.createConversation(listing.id)
      onOpenConversation?.(conversation.id)
    } catch (error) {
      setActionError(getErrorMessage(error))
    } finally {
      setIsActionPending(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="listing-dialog"
      aria-labelledby="listing-dialog-title"
      onCancel={onClose}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault()
          onClose()
        }
      }}
    >
      <div className="listing-dialog-card">
        <button
          className="listing-dialog-close"
          type="button"
          aria-label="Закрыть объявление"
          onClick={onClose}
        >
          ×
        </button>
        <ListingPhoto listing={listing} large />
        <div className="listing-dialog-content">
          <div className="listing-dialog-tags">
            <span className="condition-tag">{CONDITION_LABELS[listing.condition] ?? listing.condition}</span>
            <span>{categoryName}</span>
            {themeName && <span>{themeName}</span>}
          </div>
          <h2 id="listing-dialog-title">{listing.title}</h2>
          <p className="listing-dialog-price">{formatPrice(listing.price)}</p>
          <p className="listing-dialog-description">{listing.description}</p>

          <dl className="listing-specs">
            <div>
              <dt>Комплектность</dt>
              <dd>{listing.completeness || 'Не указана'}</dd>
            </div>
            <div>
              <dt>Недостающие детали</dt>
              <dd>{listing.missing_parts || 'Не указаны'}</dd>
            </div>
            <div>
              <dt>Коробка</dt>
              <dd>{listing.has_box ? 'Есть' : 'Нет'}</dd>
            </div>
            <div>
              <dt>Инструкция</dt>
              <dd>{listing.has_instructions ? 'Есть' : 'Нет'}</dd>
            </div>
            {listing.known_defects && (
              <div>
                <dt>Известные дефекты</dt>
                <dd>{listing.known_defects}</dd>
              </div>
            )}
          </dl>
          {user?.id === listing.seller_id ? (
            <p className="listing-action-note">Это ваше объявление</p>
          ) : listing.status === 'ACTIVE' &&
            (onDealCreated || onOpenConversation || onOpenOffers) && (
            <section className="listing-actions" aria-label="Действия с объявлением">
              <h3>Заинтересовало объявление?</h3>
              <div className="listing-action-buttons">
                <button
                  type="button"
                  className="listing-action-primary"
                  disabled={isActionPending}
                  onClick={() => void createDeal('ONLINE_PROTECTED')}
                >
                  Купить с защитой
                </button>
                <button
                  type="button"
                  className="listing-action-secondary"
                  disabled={isActionPending}
                  onClick={() => void createDeal('OFFLINE')}
                >
                  Договориться о встрече
                </button>
                <button
                  type="button"
                  className="listing-action-secondary"
                  disabled={isActionPending}
                  onClick={() => void startConversation()}
                >
                  Написать продавцу
                </button>
              </div>
              <form className="listing-offer-form" onSubmit={createOffer}>
                <label>
                  <span>Предложить свою цену, ₽</span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    required
                    value={offerAmount}
                    onChange={(event) => setOfferAmount(event.target.value)}
                  />
                </label>
                <button type="submit" className="listing-action-secondary" disabled={isActionPending}>
                  Отправить предложение
                </button>
              </form>
              {actionError && <p className="listing-action-error" role="alert">{actionError}</p>}
              {actionMessage && <p className="listing-action-success" role="status">{actionMessage}</p>}
            </section>
          )}
          <section className="listing-review-summary" aria-label="Отзывы о продавце">
            <div>
              <h3>Отзывы о продавце</h3>
              {sellerReviews ? (
                <p>
                  {sellerReviews.average_rating
                    ? `${Number(sellerReviews.average_rating).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} из 5`
                    : 'Пока нет оценок'}
                  {' '}· {sellerReviews.total} отзывов
                </p>
              ) : reviewError ? (
                <p className="listing-review-error">{reviewError}</p>
              ) : (
                <p>Загружаем отзывы...</p>
              )}
            </div>
            {sellerReviews && sellerReviews.reviews.length > 0 && (
              <ul>
                {sellerReviews.reviews.slice(0, 3).map((review) => (
                  <li key={review.id}>
                    <strong>{review.rating}/5</strong>
                    <span>{review.comment || 'Без комментария'}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </dialog>
  )
}

export default function CatalogPage({
  user,
  onRequestAuth,
  onDealCreated,
  onOpenConversation,
  onOpenOffers,
}: CatalogPageProps) {
  const [categories, setCategories] = useState<CatalogCategory[]>([])
  const [themes, setThemes] = useState<CatalogTheme[]>([])
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null)
  const [filterError, setFilterError] = useState<string | null>(null)
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set())
  const [favoriteOwnerId, setFavoriteOwnerId] = useState<string | null>(null)
  const [favoriteError, setFavoriteError] = useState<string | null>(null)
  const [favoriteActionError, setFavoriteActionError] = useState<string | null>(null)
  const [favoritePendingIds, setFavoritePendingIds] = useState<Set<string>>(new Set())
  const [listingsPage, setListingsPage] = useState<ListingPageData | null>(null)
  const [listingsError, setListingsError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [areTaxonomiesLoading, setAreTaxonomiesLoading] = useState(true)
  const [draftFilters, setDraftFilters] = useState<ListingFilters>(INITIAL_FILTERS)
  const [filters, setFilters] = useState<ListingFilters>(INITIAL_FILTERS)
  const [page, setPage] = useState(1)
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
  const [requestRevision, setRequestRevision] = useState(0)
  const [favoriteRevision, setFavoriteRevision] = useState(0)

  useEffect(() => {
    let active = true
    catalogApi
      .getListings(filters, page, PAGE_SIZE)
      .then((result) => {
        if (active) {
          setListingsPage(result)
          setListingsError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setListingsError(getErrorMessage(error))
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
  }, [filters, page, requestRevision])

  useEffect(() => {
    let active = true
    Promise.all([catalogApi.getCategories(), catalogApi.getThemes()])
      .then(([categoryList, themeList]) => {
        if (active) {
          setCategories(categoryList)
          setThemes(themeList)
          setTaxonomyError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setTaxonomyError(getErrorMessage(error))
        }
      })
      .finally(() => {
        if (active) {
          setAreTaxonomiesLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [requestRevision])

  useEffect(() => {
    let active = true
    if (!user) {
      return () => {
        active = false
      }
    }

    catalogApi
      .getFavoriteIds()
      .then((ids) => {
        if (active) {
          setFavoriteIds(ids)
          setFavoriteOwnerId(user.id)
          setFavoriteError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setFavoriteError(getErrorMessage(error))
          setFavoriteOwnerId(user.id)
          setFavoriteIds(new Set())
        }
      })

    return () => {
      active = false
    }
  }, [favoriteRevision, user])

  function updateDraftFilter<K extends keyof ListingFilters>(
    key: K,
    value: ListingFilters[K],
  ) {
    setFilterError(null)
    setDraftFilters((current) => ({ ...current, [key]: value }))
  }

  async function toggleFavorite(listingId: string) {
    if (!user) {
      onRequestAuth()
      return
    }

    if (favoriteOwnerId !== user.id) {
      return
    }

    const removing = favoriteIds.has(listingId)
    setFavoriteActionError(null)
    setFavoritePendingIds((current) => new Set(current).add(listingId))

    try {
      if (removing) {
        await catalogApi.removeFavorite(listingId)
      } else {
        await catalogApi.addFavorite(listingId)
      }
      setFavoriteIds((current) => {
        const next = new Set(current)
        if (removing) {
          next.delete(listingId)
        } else {
          next.add(listingId)
        }
        return next
      })
    } catch (error) {
      setFavoriteActionError(getErrorMessage(error))
    } finally {
      setFavoritePendingIds((current) => {
        const next = new Set(current)
        next.delete(listingId)
        return next
      })
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      draftFilters.min_price &&
      draftFilters.max_price &&
      Number(draftFilters.min_price) > Number(draftFilters.max_price)
    ) {
      setFilterError('Минимальная цена не может быть больше максимальной.')
      return
    }
    setFilterError(null)
    setListingsError(null)
    setIsLoading(true)
    setPage(1)
    setSelectedListing(null)
    setFilters({ ...draftFilters })
  }

  function clearFilters() {
    setFilterError(null)
    setListingsError(null)
    setIsLoading(true)
    setPage(1)
    setSelectedListing(null)
    setDraftFilters({ ...INITIAL_FILTERS })
    setFilters({ ...INITIAL_FILTERS })
  }

  function changePage(nextPage: number) {
    setIsLoading(true)
    setSelectedListing(null)
    setPage(nextPage)
  }

  function retryCatalog() {
    setFilterError(null)
    setListingsError(null)
    setTaxonomyError(null)
    setIsLoading(true)
    setAreTaxonomiesLoading(true)
    setRequestRevision((revision) => revision + 1)
    if (user) {
      setFavoriteRevision((revision) => revision + 1)
    }
  }

  const total = listingsPage?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="catalog-page" aria-labelledby="catalog-title">
      <div className="catalog-intro">
        <div>
          <p className="catalog-eyebrow">
            <span className="catalog-eyebrow-dot" />
            КОЛЛЕКЦИОНЕРЫ НАХОДЯТ СВОЁ
          </p>
          <h1 id="catalog-title">
            Каталог <span>находок</span>
          </h1>
          <p className="catalog-intro-copy">
            Наборы, минифигурки и детали от других коллекционеров.
          </p>
        </div>
        <div className="catalog-intro-mark" aria-hidden="true">
          <span>01</span>
          <span>КАТАЛОГ</span>
        </div>
      </div>

      <form className="catalog-search" onSubmit={applyFilters}>
        <label className="catalog-search-field">
          <span className="search-icon" aria-hidden="true" />
          <input
            type="search"
            name="q"
            aria-label="Поиск по объявлениям"
            placeholder="Найти набор, минифигурку или деталь"
            value={draftFilters.q}
            onChange={(event) => updateDraftFilter('q', event.target.value)}
          />
        </label>
        <button type="submit" className="catalog-search-button">
          Найти
        </button>
      </form>

      {(taxonomyError || listingsError || favoriteError || favoriteActionError) && (
        <div className="catalog-alert" role="alert">
          <span>{taxonomyError ?? listingsError ?? favoriteError ?? favoriteActionError}</span>
          <button type="button" onClick={retryCatalog}>Повторить</button>
        </div>
      )}

      <div className="catalog-layout">
        <aside className="filter-sidebar" aria-label="Фильтры каталога">
          <form className="filter-card" onSubmit={applyFilters}>
            <div className="filter-card-heading">
              <div>
                <p>ПОДБОР</p>
                <h2>Фильтры</h2>
              </div>
              <button type="button" className="filter-reset" onClick={clearFilters}>
                Сбросить
              </button>
            </div>

            <label className="filter-field">
              <span>Категория</span>
              <select
                value={draftFilters.category_id}
                disabled={areTaxonomiesLoading}
                onChange={(event) => updateDraftFilter('category_id', event.target.value)}
              >
                <option value="">Все категории</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </label>

            <label className="filter-field">
              <span>Тема</span>
              <select
                value={draftFilters.theme_id}
                disabled={areTaxonomiesLoading}
                onChange={(event) => updateDraftFilter('theme_id', event.target.value)}
              >
                <option value="">Все темы</option>
                {themes.map((theme) => (
                  <option key={theme.id} value={theme.id}>{theme.name}</option>
                ))}
              </select>
            </label>

            <label className="filter-field">
              <span>Состояние</span>
              <select
                value={draftFilters.condition}
                onChange={(event) => updateDraftFilter('condition', event.target.value)}
              >
                <option value="">Любое состояние</option>
                <option value="NEW">Новый</option>
                <option value="USED">Б/у</option>
                <option value="RESTORATION">На восстановление</option>
              </select>
            </label>

            <fieldset className="price-filter">
              <legend>Цена, ₽</legend>
              <label>
                <span className="visually-hidden">Минимальная цена</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  placeholder="От"
                  value={draftFilters.min_price}
                  onChange={(event) => updateDraftFilter('min_price', event.target.value)}
                />
              </label>
              <span className="price-separator">-</span>
              <label>
                <span className="visually-hidden">Максимальная цена</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  placeholder="До"
                  value={draftFilters.max_price}
                  onChange={(event) => updateDraftFilter('max_price', event.target.value)}
                />
              </label>
            </fieldset>

            {filterError && (
              <p className="filter-error" role="alert">{filterError}</p>
            )}

            <label className="filter-field">
              <span>Сортировка</span>
              <select
                value={draftFilters.sort}
                onChange={(event) => updateDraftFilter('sort', event.target.value)}
              >
                <option value="newest">Сначала новые</option>
                <option value="price_asc">Сначала дешевле</option>
                <option value="price_desc">Сначала дороже</option>
              </select>
            </label>

            <button type="submit" className="apply-filters-button">
              Показать объявления
              <span aria-hidden="true">↗</span>
            </button>
          </form>

          <div className="filter-note">
            <span className="filter-note-mark" aria-hidden="true">✳</span>
            <p>Каждая коллекция начинается с одной находки.</p>
          </div>
        </aside>

        <section className="listing-results" aria-label="Объявления">
          <div className="results-heading" aria-live="polite">
            <div>
              <p>ВЫБРАНО ДЛЯ ВАС</p>
              <h2>{formatListingCount(total)}</h2>
            </div>
            {total > 0 && (
              <span className="results-page">
                Страница {page} из {pageCount}
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="catalog-state" role="status">
              <span className="catalog-spinner" />
              <p>Загружаем объявления...</p>
            </div>
          ) : listingsError ? (
            <div className="catalog-state catalog-state-error">
              <span className="empty-icon" aria-hidden="true">!</span>
              <h3>Каталог временно недоступен</h3>
              <p>{listingsError}</p>
              <button type="button" onClick={retryCatalog}>Попробовать снова</button>
            </div>
          ) : total === 0 ? (
            <div className="catalog-state">
              <span className="empty-icon" aria-hidden="true">⌕</span>
              <h3>Ничего не нашлось</h3>
              <p>Измените запрос или сбросьте фильтры, чтобы увидеть больше объявлений.</p>
              <button type="button" onClick={clearFilters}>Сбросить фильтры</button>
            </div>
          ) : (
            <div className="listing-grid">
              {listingsPage?.items.map((listing) => {
                const categoryName =
                  categories.find((category) => category.id === listing.category_id)?.name ??
                  'LEGO'
                const themeName =
                  themes.find((theme) => theme.id === listing.theme_id)?.name ?? null
                return (
                  <ListingCard
                    key={listing.id}
                    listing={listing}
                    categoryName={categoryName}
                    themeName={themeName}
                    isFavorite={favoriteOwnerId === user?.id && favoriteIds.has(listing.id)}
                    isFavoritePending={favoritePendingIds.has(listing.id)}
                    favoriteStateLoading={Boolean(user && favoriteOwnerId !== user.id)}
                    onToggleFavorite={() => toggleFavorite(listing.id)}
                    onOpen={() => setSelectedListing(listing)}
                  />
                )
              })}
            </div>
          )}

          {!isLoading && !listingsError && pageCount > 1 && (
            <nav className="pagination" aria-label="Страницы каталога">
              <button
                type="button"
                onClick={() => changePage(page - 1)}
                disabled={page <= 1}
              >
                ← Назад
              </button>
              <span>{page} / {pageCount}</span>
              <button
                type="button"
                onClick={() => changePage(page + 1)}
                disabled={page >= pageCount}
              >
                Далее →
              </button>
            </nav>
          )}
        </section>
      </div>

      {selectedListing && (
        <ListingDialog
          listing={selectedListing}
          categoryName={
            categories.find((category) => category.id === selectedListing.category_id)?.name ??
            'LEGO'
          }
          themeName={
            themes.find((theme) => theme.id === selectedListing.theme_id)?.name ?? null
          }
          user={user}
          onRequestAuth={onRequestAuth}
          onDealCreated={onDealCreated}
          onOpenConversation={onOpenConversation}
          onOpenOffers={onOpenOffers}
          onClose={() => setSelectedListing(null)}
        />
      )}
    </section>
  )
}

export function FavoritesPage({
  user,
  onRequestAuth,
  onViewCatalog,
}: FavoritesPageProps) {
  const [categories, setCategories] = useState<CatalogCategory[]>([])
  const [themes, setThemes] = useState<CatalogTheme[]>([])
  const [pageData, setPageData] = useState<ListingPageData | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const [page, setPage] = useState(1)
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
  const [requestRevision, setRequestRevision] = useState(0)
  const [taxonomyRevision, setTaxonomyRevision] = useState(0)
  const [loadedRequestKey, setLoadedRequestKey] = useState('')
  const userId = user?.id
  const requestKey = userId ? `${userId}:${page}:${requestRevision}` : ''
  const isLoading = Boolean(userId) && loadedRequestKey !== requestKey

  useEffect(() => {
    let active = true
    if (!userId) {
      return () => {
        active = false
      }
    }

    catalogApi
      .getFavorites(page, PAGE_SIZE)
      .then((favorites) => {
        if (active) {
          setPageData(favorites)
          setErrorMessage(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(getErrorMessage(error))
        }
      })
      .finally(() => {
        if (active) {
          setLoadedRequestKey(requestKey)
        }
      })

    return () => {
      active = false
    }
  }, [page, requestKey, userId])

  useEffect(() => {
    let active = true
    if (!userId) {
      return () => {
        active = false
      }
    }

    Promise.all([catalogApi.getCategories(), catalogApi.getThemes()])
      .then(([categoryList, themeList]) => {
        if (active) {
          setCategories(categoryList)
          setThemes(themeList)
          setTaxonomyError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setTaxonomyError(getErrorMessage(error))
        }
      })

    return () => {
      active = false
    }
  }, [taxonomyRevision, userId])

  async function removeFavorite(listingId: string) {
    setPendingIds((current) => new Set(current).add(listingId))
    setErrorMessage(null)

    try {
      await catalogApi.removeFavorite(listingId)
      const currentItems = pageData?.items.length ?? 0
      setPageData((current) => current
        ? {
            ...current,
            items: current.items.filter((listing) => listing.id !== listingId),
            total: Math.max(0, current.total - 1),
          }
        : current)
      if (currentItems === 1 && page > 1) {
        setPage((current) => current - 1)
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setPendingIds((current) => {
        const next = new Set(current)
        next.delete(listingId)
        return next
      })
    }
  }

  const total = userId ? pageData?.total ?? 0 : 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="catalog-page favorites-page" aria-labelledby="favorites-title">
      <div className="catalog-intro">
        <div>
          <p className="catalog-eyebrow">
            <span className="catalog-eyebrow-dot" />
            СОХРАНЁННЫЕ НАХОДКИ
          </p>
          <h1 id="favorites-title">
            Ваше <span>избранное</span>
          </h1>
          <p className="catalog-intro-copy">
            Объявления, к которым хочется вернуться.
          </p>
        </div>
        <div className="catalog-intro-mark" aria-hidden="true">
          <span>♥</span>
          <span>ВАШ СПИСОК</span>
        </div>
      </div>

      {(errorMessage || taxonomyError) && (
        <div className="catalog-alert" role="alert">
          <span>{errorMessage ?? taxonomyError}</span>
          <button type="button" onClick={() => {
            setErrorMessage(null)
            setTaxonomyError(null)
            setRequestRevision((current) => current + 1)
            setTaxonomyRevision((current) => current + 1)
          }}>
            Повторить
          </button>
        </div>
      )}

      {!userId ? (
        <div className="catalog-state favorites-login-state">
          <span className="empty-icon" aria-hidden="true">♥</span>
          <h3>Войдите, чтобы открыть избранное</h3>
          <p>Сохраняйте интересные объявления и возвращайтесь к ним позже.</p>
          <button type="button" onClick={onRequestAuth}>Войти в аккаунт</button>
        </div>
      ) : isLoading ? (
        <div className="catalog-state" role="status">
          <span className="catalog-spinner" />
          <p>Загружаем избранное...</p>
        </div>
      ) : errorMessage ? (
        <div className="catalog-state catalog-state-error">
          <span className="empty-icon" aria-hidden="true">!</span>
          <h3>Не удалось загрузить избранное</h3>
          <p>{errorMessage}</p>
        </div>
      ) : total === 0 ? (
        <div className="catalog-state">
          <span className="empty-icon" aria-hidden="true">♡</span>
          <h3>В избранном пока пусто</h3>
          <p>Добавьте понравившиеся объявления, чтобы не потерять их.</p>
          <button type="button" onClick={onViewCatalog}>Перейти в каталог</button>
        </div>
      ) : (
        <>
          <div className="favorites-results-heading" aria-live="polite">
            <h2>{formatListingCount(total)}</h2>
            <span>Страница {page} из {pageCount}</span>
          </div>
          <div className="listing-grid">
            {pageData?.items.map((listing) => {
              const categoryName =
                categories.find((category) => category.id === listing.category_id)?.name ??
                'LEGO'
              const themeName =
                themes.find((theme) => theme.id === listing.theme_id)?.name ?? null
              return (
                <ListingCard
                  key={listing.id}
                  listing={listing}
                  categoryName={categoryName}
                  themeName={themeName}
                  isFavorite
                  isFavoritePending={pendingIds.has(listing.id)}
                  favoriteStateLoading={false}
                  onToggleFavorite={() => removeFavorite(listing.id)}
                  onOpen={() => setSelectedListing(listing)}
                />
              )
            })}
          </div>

          {pageCount > 1 && (
            <nav className="pagination" aria-label="Страницы избранного">
              <button
                type="button"
                onClick={() => setPage((current) => current - 1)}
                disabled={page <= 1}
              >
                ← Назад
              </button>
              <span>{page} / {pageCount}</span>
              <button
                type="button"
                onClick={() => setPage((current) => current + 1)}
                disabled={page >= pageCount}
              >
                Далее →
              </button>
            </nav>
          )}
        </>
      )}

      {selectedListing && (
        <ListingDialog
          listing={selectedListing}
          categoryName={
            categories.find((category) => category.id === selectedListing.category_id)?.name ??
            'LEGO'
          }
          themeName={
            themes.find((theme) => theme.id === selectedListing.theme_id)?.name ?? null
          }
          onClose={() => setSelectedListing(null)}
        />
      )}
    </section>
  )
}
