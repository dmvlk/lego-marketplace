import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { authApi, getImageUrl } from '../api'
import type { UserProfile } from '../api'
import './ProfileDialog.css'

interface ProfileDialogProps {
  user: UserProfile
  onUpdated: (profile: UserProfile) => void
  onClose: () => void
}

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Не удалось связаться с сервером. Проверьте подключение и адрес API.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Не удалось сохранить профиль. Попробуйте ещё раз.'
}

function ProfilePreview({ reference }: { reference: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <img
      className="profile-avatar-preview"
      src={getImageUrl(reference)}
      alt=""
      onError={() => setFailed(true)}
    />
  )
}

export default function ProfileDialog({ user, onUpdated, onClose }: ProfileDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [displayName, setDisplayName] = useState(user.display_name)
  const [avatarReference, setAvatarReference] = useState(user.avatar_reference ?? '')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => {
      if (dialog?.open) dialog.close()
    }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError(null)
    try {
      const profile = await authApi.updateProfile({
        display_name: displayName.trim(),
        avatar_reference: avatarReference.trim() || null,
      })
      onUpdated(profile)
      onClose()
    } catch (saveError) {
      setError(getErrorMessage(saveError))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="profile-dialog"
      aria-labelledby="profile-dialog-title"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
    >
      <form className="profile-dialog-card" onSubmit={submit}>
        <button
          className="profile-dialog-close"
          type="button"
          aria-label="Закрыть профиль"
          onClick={onClose}
        >
          ×
        </button>
        <p className="profile-dialog-eyebrow">ВАШ АККАУНТ</p>
        <h2 id="profile-dialog-title">Профиль</h2>
        <p className="profile-dialog-email">{user.email}</p>
        {avatarReference.trim() && (
          <ProfilePreview key={avatarReference.trim()} reference={avatarReference.trim()} />
        )}
        <label className="profile-dialog-field">
          <span>Отображаемое имя</span>
          <input
            required
            minLength={2}
            maxLength={100}
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </label>
        <label className="profile-dialog-field">
          <span>Ссылка на изображение профиля</span>
          <input
            maxLength={500}
            value={avatarReference}
            onChange={(event) => setAvatarReference(event.target.value)}
            placeholder="URL или путь изображения"
          />
        </label>
        {error && <p className="profile-dialog-error" role="alert">{error}</p>}
        <div className="profile-dialog-actions">
          <button type="button" className="profile-dialog-secondary" onClick={onClose}>
            Закрыть
          </button>
          <button type="submit" className="profile-dialog-primary" disabled={isSaving}>
            {isSaving ? 'Сохраняем...' : 'Сохранить'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
