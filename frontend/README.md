# Фронтенд БрикМаркет

Клиентская часть на React, TypeScript и Vite. Первый этап включает регистрацию, вход, просмотр профиля и выход из аккаунта.

## Запуск

Сначала запустите API и сервисы из корня проекта:

```powershell
docker compose up --build -d
```

Затем в каталоге `frontend` установите зависимости и запустите Vite:

```powershell
npm install
npm run dev
```

Откройте `http://localhost:5173`. Адрес API по умолчанию - `http://localhost:8000/api/v1`. Его можно изменить через переменную `VITE_API_URL` в локальном `.env`.

## Проверки

```powershell
npm run lint
npm run build
```

Токены хранятся в `sessionStorage` текущей вкладки. При истечении access-токена клиент использует refresh-токен и сохраняет новую пару.
