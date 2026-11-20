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

export interface CatalogCategory {
  id: string
  name: string
  slug: string
}

export interface CatalogTheme {
  id: string
  name: string
  slug: string
}

export interface Listing {
  id: string
  seller_id: string
  category_id: string
  theme_id: string | null
  title: string
  description: string
  price: string
  condition: string
  completeness: string | null
  missing_parts: string | null
  has_box: boolean
  has_instructions: boolean
  known_defects: string | null
  status: string
  image_references: string[]
}

export interface ListingPage {
  items: Listing[]
  total: number
  page: number
  page_size: number
}

export interface ListingFilters {
  q: string
  category_id: string
  theme_id: string
  condition: string
  min_price: string
  max_price: string
  sort: string
}

export interface ListingPayload {
  category_id: string
  theme_id: string | null
  title: string
  description: string
  price: string
  condition: string
  completeness: string | null
  missing_parts: string | null
  has_box: boolean
  has_instructions: boolean
  known_defects: string | null
}

export type TransactionType = 'OFFLINE' | 'ONLINE_PROTECTED'
export type DealStatus =
  | 'PENDING_CONFIRMATION'
  | 'AWAITING_PAYMENT'
  | 'PAID'
  | 'SHIPPED'
  | 'INSPECTION'
  | 'DISPUTED'
  | 'COMPLETED'
  | 'CANCELLED'

export interface DealSnapshot {
  title: string
  description: string
  listed_price: string
  condition: string
  completeness: string | null
  missing_parts: string | null
  has_box: boolean
  has_instructions: boolean
  known_defects: string | null
  image_references: string[]
}

export interface Deal {
  id: string
  listing_id: string
  buyer_id: string
  seller_id: string
  source_offer_id: string | null
  agreed_price: string
  transaction_type: TransactionType
  status: DealStatus
  buyer_confirmed: boolean
  seller_confirmed: boolean
  snapshot: DealSnapshot
  inspection_deadline_at: string | null
  shipment_id: string | null
}

export type OfferStatus = 'OPEN' | 'COUNTERED' | 'ACCEPTED' | 'REJECTED'

export interface Offer {
  id: string
  listing_id: string
  buyer_id: string
  seller_id: string
  sender_id: string
  recipient_id: string
  previous_offer_id: string | null
  amount: string
  status: OfferStatus
}

export type ShipmentStatus =
  | 'CREATED'
  | 'IN_TRANSIT'
  | 'OUT_FOR_DELIVERY'
  | 'EXCEPTION'
  | 'RETURNED'
  | 'DELIVERED'

export interface TrackingEvent {
  id: string
  status: ShipmentStatus
  tracking_number: string | null
  note: string | null
  created_at: string
}

export interface Shipment {
  id: string
  deal_id: string
  buyer_id: string
  seller_id: string
  carrier: string
  tracking_number: string | null
  status: ShipmentStatus
  delivered_at: string | null
  created_at: string
  updated_at: string
  tracking_events: TrackingEvent[]
}

export interface Payment {
  id: string
  deal_id: string
  buyer_id: string
  seller_id: string
  buyer_amount: string
  platform_fee: string
  seller_payout: string
  currency: string
  provider: string
  status: string
  created_at: string
  demo_mode: boolean
  demo_notice: string
}

export interface Conversation {
  id: string
  listing_id: string
  buyer_id: string
  seller_id: string
  created_at: string
  updated_at: string
  unread_count: number
}

export interface ChatMessage {
  id: string
  conversation_id: string
  sender_id: string
  content: string
  created_at: string
}

export type DisputeReason =
  | 'NOT_AS_DESCRIBED'
  | 'DAMAGED'
  | 'MISSING_PARTS'
  | 'WRONG_ITEM'
  | 'NOT_DELIVERED'
  | 'OTHER'

export type DisputeStatus =
  | 'WAITING_SELLER'
  | 'WAITING_BUYER'
  | 'UNDER_REVIEW'
  | 'RESOLVING'
  | 'RESOLVED'

export type EvidenceType = 'TEXT' | 'MESSAGE' | 'TRACKING'
export type DisputeDecision = 'REFUND_BUYER' | 'PAY_SELLER' | 'PARTIAL_REFUND'

export interface DisputeEvidence {
  id: string
  submitted_by: string
  evidence_type: 'TEXT' | 'MESSAGE' | 'TRACKING' | 'IMAGE'
  content: string
  created_at: string
  image_url: string | null
}

export interface Dispute {
  id: string
  deal_id: string
  opened_by: string
  reason: DisputeReason
  description: string
  status: DisputeStatus
  response_due_at: string | null
  deadline_missed_at: string | null
  resolution: DisputeDecision | null
  refund_amount: string | null
  resolved_by: string | null
  resolved_at: string | null
  resolution_note: string | null
  created_at: string
  evidence: DisputeEvidence[]
}

export interface DisputeAuditEntry {
  id: string
  actor_id: string | null
  action: string
  details: Record<string, unknown>
  created_at: string
}

export interface Review {
  id: string
  deal_id: string
  reviewer_id: string
  seller_id: string
  rating: number
  comment: string | null
  created_at: string
}

export interface SellerReviews {
  seller_id: string
  total: number
  average_rating: string | number | null
  reviews: Review[]
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

export function getImageUrl(reference: string): string {
  return new URL(reference, API_BASE_URL).href
}

export async function getPrivateImageUrl(reference: string): Promise<string> {
  const baseUrl = new URL(API_BASE_URL)
  const imageUrl = new URL(reference, API_BASE_URL)
  const basePath = baseUrl.pathname.replace(/\/+$/, '')
  const path = imageUrl.pathname.startsWith(basePath)
    ? imageUrl.pathname.slice(basePath.length)
    : imageUrl.pathname
  const response = await send(`${path}${imageUrl.search}`, { method: 'GET' }, true)
  return URL.createObjectURL(await response.blob())
}

export function getWebSocketUrl(path: string): string {
  const url = new URL(`${API_BASE_URL}${path}`)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.href
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
    if (typeof init.body === 'string' && !headers.has('Content-Type')) {
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
  updateProfile(payload: Pick<UserProfile, 'display_name' | 'avatar_reference'>): Promise<UserProfile> {
    return requestJson(
      '/users/me',
      { method: 'PATCH', body: JSON.stringify(payload) },
      true,
    )
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

export const catalogApi = {
  getCategories(): Promise<CatalogCategory[]> {
    return requestJson('/catalog/categories', { method: 'GET' })
  },
  getThemes(): Promise<CatalogTheme[]> {
    return requestJson('/catalog/themes', { method: 'GET' })
  },
  getListings(
    filters: ListingFilters,
    page: number,
    pageSize: number,
  ): Promise<ListingPage> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      sort: filters.sort,
    })
    if (filters.q.trim()) params.set('q', filters.q.trim())
    if (filters.category_id) params.set('category_id', filters.category_id)
    if (filters.theme_id) params.set('theme_id', filters.theme_id)
    if (filters.condition) params.set('condition', filters.condition)
    if (filters.min_price) params.set('min_price', filters.min_price)
    if (filters.max_price) params.set('max_price', filters.max_price)
    return requestJson(`/catalog/listings?${params.toString()}`, { method: 'GET' })
  },
  getListing(listingId: string): Promise<Listing> {
    return requestJson(`/catalog/listings/${listingId}`, { method: 'GET' })
  },
  getMyListings(page: number, pageSize: number): Promise<ListingPage> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    return requestJson(`/catalog/my-listings?${params.toString()}`, { method: 'GET' }, true)
  },
  createListing(payload: ListingPayload): Promise<Listing> {
    return requestJson(
      '/catalog/listings',
      { method: 'POST', body: JSON.stringify(payload) },
      true,
    )
  },
  updateListing(listingId: string, payload: ListingPayload): Promise<Listing> {
    return requestJson(
      `/catalog/listings/${listingId}`,
      { method: 'PATCH', body: JSON.stringify(payload) },
      true,
    )
  },
  uploadListingImage(listingId: string, file: File): Promise<{
    image_id: string
    image_reference: string
  }> {
    const formData = new FormData()
    formData.append('file', file)
    return requestJson(
      `/catalog/listings/${listingId}/images`,
      { method: 'POST', body: formData },
      true,
    )
  },
  async archiveListing(listingId: string): Promise<void> {
    await send(`/catalog/listings/${listingId}`, { method: 'DELETE' }, true)
  },
  getFavorites(page: number, pageSize: number): Promise<ListingPage> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    return requestJson(`/catalog/favorites?${params.toString()}`, { method: 'GET' }, true)
  },
  async getFavoriteIds(): Promise<Set<string>> {
    const pageSize = 100
    const firstPage = await this.getFavorites(1, pageSize)
    const pageCount = Math.ceil(firstPage.total / pageSize)
    const listingIds = firstPage.items.map((listing) => listing.id)
    for (let batchStartPage = 2; batchStartPage <= pageCount; batchStartPage += 10) {
      const pageNumbers = Array.from(
        { length: Math.min(10, pageCount - batchStartPage + 1) },
        (_, index) => batchStartPage + index,
      )
      const pages = await Promise.all(
        pageNumbers.map((pageNumber) => this.getFavorites(pageNumber, pageSize)),
      )
      listingIds.push(...pages.flatMap((page) => page.items.map((listing) => listing.id)))
    }
    return new Set(listingIds)
  },
  addFavorite(listingId: string): Promise<{ status: string }> {
    return requestJson(
      `/catalog/listings/${listingId}/favorites`,
      { method: 'POST' },
      true,
    )
  },
  async removeFavorite(listingId: string): Promise<void> {
    await send(
      `/catalog/listings/${listingId}/favorites`,
      { method: 'DELETE' },
      true,
    )
  },
}

export const dealsApi = {
  listOffers(): Promise<Offer[]> {
    return requestJson('/offers?page=1&page_size=100', { method: 'GET' }, true)
  },
  createOffer(payload: { listing_id: string; amount: string }): Promise<Offer> {
    return requestJson('/offers', { method: 'POST', body: JSON.stringify(payload) }, true)
  },
  counterOffer(offerId: string, amount: string): Promise<Offer> {
    return requestJson(
      `/offers/${offerId}/counter`,
      { method: 'POST', body: JSON.stringify({ amount }) },
      true,
    )
  },
  async rejectOffer(offerId: string): Promise<void> {
    await send(`/offers/${offerId}/reject`, { method: 'POST' }, true)
  },
  acceptOffer(offerId: string, transaction_type: TransactionType): Promise<Deal> {
    return requestJson(
      `/offers/${offerId}/accept?transaction_type=${transaction_type}`,
      { method: 'POST' },
      true,
    )
  },
  createDeal(payload: { listing_id: string; transaction_type: TransactionType }): Promise<Deal> {
    return requestJson('/deals', { method: 'POST', body: JSON.stringify(payload) }, true)
  },
  getPurchases(): Promise<Deal[]> {
    return requestJson('/deals/purchases?page=1&page_size=100', { method: 'GET' }, true)
  },
  getSales(): Promise<Deal[]> {
    return requestJson('/deals/sales?page=1&page_size=100', { method: 'GET' }, true)
  },
  getDeal(dealId: string): Promise<Deal> {
    return requestJson(`/deals/${dealId}`, { method: 'GET' }, true)
  },
  getDealDispute(dealId: string): Promise<Dispute | null> {
    return requestJson(`/deals/${dealId}/dispute`, { method: 'GET' }, true)
  },
  confirmOffline(dealId: string): Promise<Deal> {
    return requestJson(`/deals/${dealId}/confirm-offline`, { method: 'POST' }, true)
  },
  cancelDeal(dealId: string): Promise<Deal> {
    return requestJson(`/deals/${dealId}/cancel`, { method: 'POST' }, true)
  },
  confirmInspection(dealId: string): Promise<Deal> {
    return requestJson(`/deals/${dealId}/inspection/confirm`, { method: 'POST' }, true)
  },
  openDispute(dealId: string, payload: { reason: DisputeReason; description: string }): Promise<Dispute> {
    return requestJson(
      `/deals/${dealId}/disputes`,
      { method: 'POST', body: JSON.stringify(payload) },
      true,
    )
  },
  getDispute(disputeId: string): Promise<Dispute> {
    return requestJson(`/disputes/${disputeId}`, { method: 'GET' }, true)
  },
  addDisputeEvidence(
    disputeId: string,
    payload: { evidence_type: EvidenceType; content: string },
  ): Promise<DisputeEvidence> {
    return requestJson(
      `/disputes/${disputeId}/evidence`,
      { method: 'POST', body: JSON.stringify(payload) },
      true,
    )
  },
  uploadDisputeImage(disputeId: string, file: File, description: string): Promise<DisputeEvidence> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('description', description)
    return requestJson(
      `/disputes/${disputeId}/evidence/images`,
      { method: 'POST', body: formData },
      true,
    )
  },
  listAdminDisputes(status?: DisputeStatus): Promise<Dispute[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : ''
    return requestJson(`/admin/disputes${query}`, { method: 'GET' }, true)
  },
  getDisputeAudit(disputeId: string): Promise<DisputeAuditEntry[]> {
    return requestJson(`/admin/disputes/${disputeId}/audit`, { method: 'GET' }, true)
  },
  requestDisputeEvidence(
    disputeId: string,
    payload: { participant: 'buyer' | 'seller'; note: string },
  ): Promise<Dispute> {
    return requestJson(
      `/admin/disputes/${disputeId}/request-evidence`,
      { method: 'POST', body: JSON.stringify(payload) },
      true,
    )
  },
  resolveDispute(
    disputeId: string,
    payload: { decision: DisputeDecision; refund_amount?: string; note: string },
  ): Promise<Dispute> {
    return requestJson(
      `/admin/disputes/${disputeId}/resolve`,
      { method: 'POST', body: JSON.stringify(payload) },
      true,
    )
  },
}

export const paymentsApi = {
  startDealPayment(dealId: string, idempotencyKey: string): Promise<Payment> {
    return requestJson(
      `/payments/deals/${dealId}`,
      { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } },
      true,
    )
  },
}

export const deliveryApi = {
  createShipment(dealId: string, carrier: string): Promise<Shipment> {
    return requestJson(
      `/deliveries/deals/${dealId}/ship`,
      { method: 'POST', body: JSON.stringify({ carrier }) },
      true,
    )
  },
  getShipmentByDeal(dealId: string): Promise<Shipment> {
    return requestJson(`/deliveries/deals/${dealId}`, { method: 'GET' }, true)
  },
  updateTracking(
    shipmentId: string,
    payload: { tracking_number?: string; status?: ShipmentStatus; note?: string },
  ): Promise<Shipment> {
    return requestJson(
      `/deliveries/${shipmentId}/tracking`,
      { method: 'PATCH', body: JSON.stringify(payload) },
      true,
    )
  },
  confirmDelivered(shipmentId: string): Promise<Shipment> {
    return requestJson(`/deliveries/${shipmentId}/delivered`, { method: 'POST' }, true)
  },
}

export const chatApi = {
  listConversations(page = 1, pageSize = 100): Promise<Conversation[]> {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    return requestJson(`/conversations?${params.toString()}`, { method: 'GET' }, true)
  },
  createConversation(listingId: string): Promise<Conversation> {
    return requestJson(
      '/conversations',
      { method: 'POST', body: JSON.stringify({ listing_id: listingId }) },
      true,
    )
  },
  listMessages(conversationId: string, page = 1): Promise<ChatMessage[]> {
    const params = new URLSearchParams({ page: String(page), page_size: '100' })
    return requestJson(
      `/conversations/${conversationId}/messages?${params.toString()}`,
      { method: 'GET' },
      true,
    )
  },
  sendMessage(conversationId: string, content: string): Promise<ChatMessage> {
    return requestJson(
      `/conversations/${conversationId}/messages`,
      { method: 'POST', body: JSON.stringify({ content }) },
      true,
    )
  },
}

export const reviewsApi = {
  createReview(dealId: string, payload: { rating: number; comment: string | null }): Promise<Review> {
    return requestJson(
      `/deals/${dealId}/review`,
      { method: 'POST', body: JSON.stringify(payload) },
      true,
    )
  },
  getSellerReviews(sellerId: string): Promise<SellerReviews> {
    return requestJson(`/users/${sellerId}/reviews`, { method: 'GET' })
  },
}
