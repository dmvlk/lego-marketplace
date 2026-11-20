import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  catalogApi,
  getImageUrl,
} from '../api'
import type {
  CatalogCategory,
  CatalogTheme,
  Listing,
  ListingPage,
  ListingPayload,
  UserProfile,
} from '../api'
import './MyListingsPage.css'

const PAGE_SIZE = 12

const CONDITIONS = [
  { value: 'NEW', label: 'Новый' },
  { value: 'USED', label: 'Б/у' },
  { value: 'RESTORATION', label: 'На восстановление' },
]

const CONDITION_LABELS: Record<string, string> = Object.fromEntries(
  CONDITIONS.map(({ value, label }) => [value, label]),
)

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Активно',
  RESERVED: 'Зарезервировано',
  SOLD: 'Продано',
  ARCHIVED: 'В архиве',
  DRAFT: 'Черновик',
  BLOCKED: 'Заблокировано',
}

const EMPTY_PAYLOAD: ListingPayload = {
  category_id: '',
  theme_id: null,
  title: '',
  description: '',
  price: '',
  condition: 'USED',
  completeness: null,
  missing_parts: null,
  has_box: false,
  has_instructions: false,
  known_defects: null,
}

interface MyListingsPageProps {
  user: UserProfile | null
  onRequestAuth: () => void
}

interface ListingEditorDialogProps {
  listing: Listing | null
  categories: CatalogCategory[]
  themes: CatalogTheme[]
  onClose: () => void
  onSaved: (listing: Listing) => void
}

interface ArchiveDialogProps {
  listing: Listing
  isArchiving: boolean
  onCancel: () => void
  onConfirm: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Не удалось связаться с сервером. Проверьте подключение и адрес API.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Не удалось выполнить операцию. Попробуйте ещё раз.'
}

function getListingPayload(listing: Listing | null): ListingPayload {
  if (!listing) {
    return { ...EMPTY_PAYLOAD }
  }
  return {
    category_id: listing.category_id,
    theme_id: listing.theme_id,
    title: listing.title,
    description: listing.description,
    price: listing.price,
    condition: listing.condition,
    completeness: listing.completeness,
    missing_parts: listing.missing_parts,
    has_box: listing.has_box,
    has_instructions: listing.has_instructions,
    known_defects: listing.known_defects,
  }
}

function formatPrice(price: string): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 2,
  }).format(Number(price))
}

function ListingThumbnail({ listing }: { listing: Listing }) {
  const [imageFailed, setImageFailed] = useState(false)
  const imageReference = listing.image_references[0]

  if (!imageReference || imageFailed) {
    return (
      <div className="seller-listing-placeholder" role="img" aria-label={`Нет фото: ${listing.title}`}>
        <span aria-hidden="true">B</span>
      </div>
    )
  }

  return (
    <img
      className="seller-listing-image"
      src={getImageUrl(imageReference)}
      alt={listing.title}
      loading="lazy"
      onError={() => setImageFailed(true)}
    />
  )
}

function ListingEditorDialog({
  listing,
  categories,
  themes,
  onClose,
  onSaved,
}: ListingEditorDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [values, setValues] = useState<ListingPayload>(() => getListingPayload(listing))
  const [selectedImages, setSelectedImages] = useState<File[]>([])
  const [savedListing, setSavedListing] = useState<Listing | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const currentListing = savedListing ?? listing

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => {
      if (dialog?.open) {
        dialog.close()
      }
    }
  }, [])

  function updateField<K extends keyof ListingPayload>(
    key: K,
    value: ListingPayload[K],
  ) {
    setValues((current) => ({ ...current, [key]: value }))
    setErrorMessage(null)
  }

  function selectImages(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    const currentCount = currentListing?.image_references.length ?? 0

    if (currentCount + selectedImages.length + files.length > 10) {
      setErrorMessage('К объявлению можно добавить не более 10 фото.')
      return
    }

    const invalidFile = files.find((file) => (
      (file.type !== '' && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) ||
      file.size > 5 * 1024 * 1024
    ))
    if (invalidFile) {
      setErrorMessage(
        invalidFile.size > 5 * 1024 * 1024
          ? `Фото «${invalidFile.name}» больше 5 МБ.`
          : `Фото «${invalidFile.name}» должно быть в формате JPEG, PNG или WebP.`,
      )
      return
    }

    setSelectedImages((current) => [...current, ...files])
    setErrorMessage(null)
  }

  async function saveListing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setErrorMessage(null)

    try {
      let updatedListing = currentListing
        ? await catalogApi.updateListing(currentListing.id, values)
        : await catalogApi.createListing(values)
      setSavedListing(updatedListing)

      let remainingImages = selectedImages
      while (remainingImages.length > 0) {
        const [file, ...rest] = remainingImages
        try {
          const uploaded = await catalogApi.uploadListingImage(updatedListing.id, file)
          updatedListing = {
            ...updatedListing,
            image_references: [...updatedListing.image_references, uploaded.image_reference],
          }
          remainingImages = rest
          setSavedListing(updatedListing)
          setSelectedImages(remainingImages)
        } catch (error) {
          setSavedListing(updatedListing)
          setSelectedImages(remainingImages)
          setErrorMessage(
            `Объявление сохранено, но фото «${file.name}» не загрузилось: ${getErrorMessage(error)}`,
          )
          return
        }
      }

      onSaved(updatedListing)
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="seller-dialog"
      aria-labelledby="listing-editor-title"
      onCancel={(event) => {
        event.preventDefault()
        if (!isSaving) {
          onClose()
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault()
          if (!isSaving) {
            onClose()
          }
        }
      }}
    >
      <div className="seller-dialog-card">
        <button
          className="seller-dialog-close"
          type="button"
          aria-label="Закрыть форму"
          disabled={isSaving}
          onClick={onClose}
        >
          ×
        </button>
        <p className="seller-dialog-eyebrow">{listing ? 'РЕДАКТИРОВАНИЕ' : 'НОВОЕ ОБЪЯВЛЕНИЕ'}</p>
        <h2 id="listing-editor-title">{listing ? 'Изменить объявление' : 'Продать находку'}</h2>
        <form className="seller-listing-form" onSubmit={saveListing}>
          <label>
            <span>Название</span>
            <input
              autoFocus
              required
              minLength={3}
              maxLength={200}
              value={values.title}
              onChange={(event) => updateField('title', event.target.value)}
            />
          </label>

          <div className="seller-form-row">
            <label>
              <span>Категория</span>
              <select
                required
                value={values.category_id}
                onChange={(event) => updateField('category_id', event.target.value)}
              >
                <option value="">Выберите категорию</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Тема</span>
              <select
                value={values.theme_id ?? ''}
                onChange={(event) => updateField('theme_id', event.target.value || null)}
              >
                <option value="">Без темы</option>
                {themes.map((theme) => (
                  <option key={theme.id} value={theme.id}>{theme.name}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="seller-form-row">
            <label>
              <span>Цена, ₽</span>
              <input
                required
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                value={values.price}
                onChange={(event) => updateField('price', event.target.value)}
              />
            </label>
            <label>
              <span>Состояние</span>
              <select
                required
                value={values.condition}
                onChange={(event) => updateField('condition', event.target.value)}
              >
                {CONDITIONS.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          </div>

          <label>
            <span>Описание</span>
            <textarea
              required
              minLength={10}
              maxLength={5000}
              rows={4}
              value={values.description}
              onChange={(event) => updateField('description', event.target.value)}
            />
          </label>

          <label>
            <span>Комплектность</span>
            <input
              maxLength={300}
              value={values.completeness ?? ''}
              onChange={(event) => updateField('completeness', event.target.value || null)}
            />
          </label>

          <label>
            <span>Недостающие детали</span>
            <textarea
              rows={2}
              value={values.missing_parts ?? ''}
              onChange={(event) => updateField('missing_parts', event.target.value || null)}
            />
          </label>

          <div className="seller-checkbox-row">
            <label>
              <input
                type="checkbox"
                checked={values.has_box}
                onChange={(event) => updateField('has_box', event.target.checked)}
              />
              <span>Есть коробка</span>
            </label>
            <label>
              <input
                type="checkbox"
                checked={values.has_instructions}
                onChange={(event) => updateField('has_instructions', event.target.checked)}
              />
              <span>Есть инструкция</span>
            </label>
          </div>

          <label>
            <span>Известные дефекты</span>
            <textarea
              rows={2}
              value={values.known_defects ?? ''}
              onChange={(event) => updateField('known_defects', event.target.value || null)}
            />
          </label>

          <label className="seller-image-field">
            <span>Фотографии</span>
            <input
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp"
              disabled={(currentListing?.image_references.length ?? 0) + selectedImages.length >= 10}
              onChange={selectImages}
            />
            <small>
              JPEG, PNG или WebP до 5 МБ. Можно добавить до 10 фото.
            </small>
          </label>

          {currentListing && currentListing.image_references.length > 0 && (
            <p className="seller-existing-images">
              Уже загружено фото: {currentListing.image_references.length}
            </p>
          )}

          {selectedImages.length > 0 && (
            <ul className="seller-selected-images">
              {selectedImages.map((file, index) => (
                <li key={`${file.name}:${file.size}:${index}`}>
                  <span>{file.name}</span>
                  <button
                    type="button"
                    aria-label={`Убрать фото ${file.name}`}
                    onClick={() => setSelectedImages((current) => current.filter((_, i) => i !== index))}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}

          {errorMessage && <p className="seller-form-error" role="alert">{errorMessage}</p>}

          <div className="seller-form-actions">
            <button type="button" className="seller-secondary-button" onClick={onClose} disabled={isSaving}>
              Отмена
            </button>
            <button type="submit" className="seller-primary-button" disabled={isSaving}>
              {isSaving ? 'Сохраняем...' : listing ? 'Сохранить изменения' : 'Опубликовать'}
            </button>
          </div>
        </form>
      </div>
    </dialog>
  )
}

function ArchiveDialog({
  listing,
  isArchiving,
  onCancel,
  onConfirm,
}: ArchiveDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => {
      if (dialog?.open) {
        dialog.close()
      }
    }
  }, [])

  return (
    <dialog
      ref={dialogRef}
      className="seller-confirm-dialog"
      aria-labelledby="archive-dialog-title"
      onCancel={(event) => {
        event.preventDefault()
        if (!isArchiving) {
          onCancel()
        }
      }}
    >
      <h2 id="archive-dialog-title">Переместить в архив?</h2>
      <p>«{listing.title}» исчезнет из каталога, но останется в ваших объявлениях.</p>
      <div className="seller-form-actions">
        <button type="button" className="seller-secondary-button" onClick={onCancel} disabled={isArchiving}>
          Оставить
        </button>
        <button
          type="button"
          className="seller-danger-button"
          onClick={() => { void onConfirm() }}
          disabled={isArchiving}
        >
          {isArchiving ? 'Переносим...' : 'В архив'}
        </button>
      </div>
    </dialog>
  )
}

export default function MyListingsPage({ user, onRequestAuth }: MyListingsPageProps) {
  const [pageData, setPageData] = useState<ListingPage | null>(null)
  const [categories, setCategories] = useState<CatalogCategory[]>([])
  const [themes, setThemes] = useState<CatalogTheme[]>([])
  const [listingsError, setListingsError] = useState<string | null>(null)
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [taxonomyRevision, setTaxonomyRevision] = useState(0)
  const [loadedRequestKey, setLoadedRequestKey] = useState('')
  const [editorListing, setEditorListing] = useState<Listing | null | undefined>(undefined)
  const [archiveListing, setArchiveListing] = useState<Listing | null>(null)
  const [isArchiving, setIsArchiving] = useState(false)
  const userId = user?.id
  const requestKey = userId ? `${userId}:${page}:${revision}` : ''
  const isLoading = Boolean(userId) && loadedRequestKey !== requestKey

  useEffect(() => {
    let active = true
    if (!userId) {
      return () => {
        active = false
      }
    }

    catalogApi
      .getMyListings(page, PAGE_SIZE)
      .then((result) => {
        if (active) {
          setPageData(result)
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

  function retry() {
    setListingsError(null)
    setTaxonomyError(null)
    setRevision((current) => current + 1)
    setTaxonomyRevision((current) => current + 1)
  }

  function handleSaved() {
    setEditorListing(undefined)
    setRevision((current) => current + 1)
  }

  async function archiveSelectedListing() {
    if (!archiveListing) {
      return
    }

    setIsArchiving(true)
    setListingsError(null)
    try {
      await catalogApi.archiveListing(archiveListing.id)
      setPageData((current) => current
        ? {
            ...current,
            items: current.items.map((listing) => listing.id === archiveListing.id
              ? { ...listing, status: 'ARCHIVED' }
              : listing),
          }
        : current)
      setArchiveListing(null)
    } catch (error) {
      setListingsError(getErrorMessage(error))
    } finally {
      setIsArchiving(false)
    }
  }

  const total = userId ? pageData?.total ?? 0 : 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="seller-page" aria-labelledby="seller-page-title">
      <header className="seller-page-heading">
        <div>
          <p className="seller-page-eyebrow">ВАША КОЛЛЕКЦИЯ</p>
          <h1 id="seller-page-title">Мои <span>объявления</span></h1>
          <p>Управляйте предложениями и добавляйте новые находки.</p>
        </div>
        {userId && (
          <button
            className="seller-primary-button seller-create-button"
            type="button"
            onClick={() => setEditorListing(null)}
          >
            + Создать объявление
          </button>
        )}
      </header>

      {(listingsError || taxonomyError) && (
        <div className="seller-alert" role="alert">
          <span>{listingsError ?? taxonomyError}</span>
          <button type="button" onClick={retry}>Повторить</button>
        </div>
      )}

      {!userId ? (
        <div className="seller-state">
          <span aria-hidden="true">▣</span>
          <h2>Войдите, чтобы управлять объявлениями</h2>
          <p>После входа вы сможете публиковать и редактировать свои предложения.</p>
          <button className="seller-primary-button" type="button" onClick={onRequestAuth}>
            Войти в аккаунт
          </button>
        </div>
      ) : isLoading ? (
        <div className="seller-state" role="status">
          <span className="seller-spinner" />
          <p>Загружаем объявления...</p>
        </div>
      ) : listingsError ? (
        <div className="seller-state seller-state-error">
          <span aria-hidden="true">!</span>
          <h2>Не удалось загрузить объявления</h2>
          <p>{listingsError}</p>
          <button className="seller-secondary-button" type="button" onClick={retry}>
            Попробовать снова
          </button>
        </div>
      ) : total === 0 ? (
        <div className="seller-state">
          <span aria-hidden="true">✳</span>
          <h2>Пока нет объявлений</h2>
          <p>Добавьте первую находку, чтобы другие коллекционеры могли её найти.</p>
          <button className="seller-primary-button" type="button" onClick={() => setEditorListing(null)}>
            Создать объявление
          </button>
        </div>
      ) : (
        <>
          <div className="seller-results-heading" aria-live="polite">
            <h2>{total} {total === 1 ? 'объявление' : total >= 2 && total <= 4 ? 'объявления' : 'объявлений'}</h2>
            <span>Страница {page} из {pageCount}</span>
          </div>

          <div className="seller-listing-grid">
            {pageData?.items.map((listing) => {
              const categoryName =
                categories.find((category) => category.id === listing.category_id)?.name ?? 'LEGO'
              const themeName =
                themes.find((theme) => theme.id === listing.theme_id)?.name
              const canEdit = listing.status === 'ACTIVE' || listing.status === 'DRAFT'
              return (
                <article className="seller-listing-card" key={listing.id}>
                  <ListingThumbnail listing={listing} />
                  <div className="seller-listing-content">
                    <div className="seller-listing-tags">
                      <span className={`seller-status seller-status-${listing.status.toLowerCase()}`}>
                        {STATUS_LABELS[listing.status] ?? listing.status}
                      </span>
                      <span>{CONDITION_LABELS[listing.condition] ?? listing.condition}</span>
                    </div>
                    <h3>{listing.title}</h3>
                    <p className="seller-listing-category">
                      {categoryName}{themeName ? ` · ${themeName}` : ''}
                    </p>
                    <strong className="seller-listing-price">{formatPrice(listing.price)}</strong>
                    <div className="seller-listing-actions">
                      {canEdit && (
                        <button
                          className="seller-secondary-button"
                          type="button"
                          onClick={() => setEditorListing(listing)}
                        >
                          Изменить
                        </button>
                      )}
                      {listing.status === 'ACTIVE' && (
                        <button
                          className="seller-archive-button"
                          type="button"
                          onClick={() => setArchiveListing(listing)}
                        >
                          В архив
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              )
            })}
          </div>

          {pageCount > 1 && (
            <nav className="pagination" aria-label="Страницы моих объявлений">
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

      {editorListing !== undefined && (
        <ListingEditorDialog
          key={editorListing?.id ?? 'new'}
          listing={editorListing}
          categories={categories}
          themes={themes}
          onClose={() => setEditorListing(undefined)}
          onSaved={handleSaved}
        />
      )}

      {archiveListing && (
        <ArchiveDialog
          listing={archiveListing}
          isArchiving={isArchiving}
          onCancel={() => setArchiveListing(null)}
          onConfirm={archiveSelectedListing}
        />
      )}
    </section>
  )
}
